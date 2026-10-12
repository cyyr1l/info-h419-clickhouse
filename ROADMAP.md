# INFO-H-419 Data Warehouses Project Roadmap (ClickHouse group)

**Team:** Bao Anh Tran, Anabelle Meli, Cyril Stembert, Paula Ventura
**Course:** INFO-H-419 Data Warehouses, Prof. Esteban Zimányi ([course page](https://cs.ulb.ac.be/public/teaching/infoh419))
**Last updated:** 5 Oct 2026. Update it after each weekly meeting.

---

## At a glance

| | Part I: TPC-DS | Part II: TPC-DI |
|---|---|---|
| What | Benchmark the 99 analytical queries on ClickHouse | Build an ETL that loads a data warehouse into ClickHouse (historical load + 2 incremental batches) |
| Hard deadline | **Sun 1 Nov 2026** | **Thu 24 Dec 2026** |
| Internal freeze | Fri 30 Oct | Fri 18 Dec |
| Hardest part | Benchmark methodology and result analysis | SCD Type 2 / UPDATE on ClickHouse; XML and fixed-width sources |

- Each part is submitted as **1 PDF report + 1 zip with the code**, plus instructions so the lecturer can rerun everything. The project is worth 30% of the grade.
- **Meetings:** kickoff on Mon 5 Oct after the lecture. Then a 30-minute meeting every Tuesday at 16:00, right after the exercise session.
- **Roles:** ① Infrastructure & Data · ② Benchmark & Measurement · ③ Data Schema · ④ Validation & Analysis. Everyone owns a technical area; documentation and coordination are shared equally (details in section 3).
- **Do first:** the kickoff checklist in section 4.

---

## 1. Project requirements

Summary of the course page:

- Two parts, groups of 3–4, same group for both parts. Deadlines are strict.
- Free choice of tools.
- **Scale factor (SF):** the official TPC scale factors are not required. Estimate the largest SF your own computer can handle and use it as the reference (1.0). Then run 3 smaller SFs (e.g. 0.1, 0.2 and 0.5 of the reference) to show how performance evolves with data size. The lecturer states the pedagogical goal: *"learn how to properly perform a benchmark"*.
- **Deliverables per part:** *"A report in pdf explaining the essential aspects of your implementation"* and *"A zip file containing the code of your implementation, with all necessary instructions to be able to replicate your implementation by the lecturer in standard computing infrastructure."*
- The page says nothing about a presentation, a page limit or a report template. Ask the lecturer (see section 8).

---

## 2. Timeline

| Week | Dates | Expected outcome by the end of the week |
|---|---|---|
| **Part I: TPC-DS** | | |
| 1 | 5–11 Oct | ClickHouse runs in Docker. dsdgen/dsqgen are built. All 24 tables load at SF 1. Trial load of SF 100 on the benchmark machine (≥ 32 GB RAM). |
| 2 | 12–18 Oct | All 99 queries run and match the reference answers at SF 1. Benchmark harness done. **Reference SF decided.** |
| 3 | 19–25 Oct | Load test, power test and throughput test done at all 4 SFs. Methodology section of the report drafted. |
| 4 | 26 Oct–1 Nov | Charts, analysis, zip, rebuild test on another machine. **Internal freeze Fri 30 Oct**, submit Sat 31 Oct. |
| **Part II: TPC-DI** | | |
| 5 | 2–8 Nov | Read the spec, generate data with DIGen, decide the ETL architecture and the DW schema. |
| 6–7 | 9–22 Nov | Historical load, one table cluster per person. |
| 8–9 | 23 Nov–6 Dec | Incremental batches 2 and 3 (with SCD Type 2), run the audit checks. |
| 10 | 7–13 Dec | Measurements at all 4 SFs. |
| 11 | 14–20 Dec | Report and zip. **Internal freeze Fri 18 Dec**, before the holidays. 21–24 Dec is buffer. |

**Scope (goal: solid and complete, no extras):**
- **Part I:** load test, power test, throughput test, and checking that query results are correct. Data maintenance only if we are ahead of schedule at the end of week 2; otherwise the report states clearly that it was not done.
- **Part II:** historical load, 2 incremental batches and the audit checks.
- No separate optimization study and no comparison with other database systems.

---

## 3. Roles and responsibilities

Everyone keeps one technical area for both parts. Documentation and coordination are shared equally among all 4. Roles are chosen at the kickoff. Whoever owns the machine with ≥ 32 GB RAM should take role ②, because that machine will run benchmarks for hours, sometimes overnight.

### Technical roles (same for both parts)

| Role | Part I: TPC-DS | Part II: TPC-DI |
|---|---|---|
| ① Infrastructure & Data | Docker, build dsdgen/dsqgen, data generation and loading scripts, reset script for cold runs, zip packaging, rebuild test on a clean machine | DIGen, loaders for each source format (CSV, XML → CSV, FINWIRE), orchestrator, zip packaging, rebuild test on a clean machine |
| ② Benchmark & Measurement | Read the execution rules and metric in the spec, write the benchmark protocol, write the Python harness (power/throughput), run the benchmarks on the benchmark machine, compute the metric | Read the execution rules and metric, time each phase and step, run the benchmarks, compute TPC_DI_RPS |
| ③ Data Schema | DDL, data types, NULL handling, sorting keys, partitioning, settings profile, fix the hard and memory-hungry queries | Staging and DW DDL, SCD2 and update strategy, surrogate keys, help the other clusters apply SCD2 |
| ④ Validation & Analysis | Generate the query sets with dsqgen, build the DuckDB reference answers, write the result comparison script, track the status of the 99 queries, analyze with `EXPLAIN`, make the charts | Port the audit script to ClickHouse, write DImessages, run the audit after each batch, make the charts |

### Shared technical work

| Role | Part I: queries | Part II: ETL table cluster (details in section 6) |
|---|---|---|
| ① | Q1–25 | Cluster A: reference tables, DimBroker, FINWIRE (DimCompany, DimSecurity, Financial) |
| ② | Q26–50 | Cluster C: DimTrade, FactCashBalances, FactHoldings |
| ③ | Q51–75 | Cluster B: DimCustomer, DimAccount, Prospect (XML and SCD2, the heaviest cluster) |
| ④ | Q76–99 | Cluster D: FactWatches, FactMarketHistory, DImessages, audit |

### Documentation and coordination (shared)
- **Writing the report:** whoever did a piece of work writes the matching report section. See the "who writes what" tables at the end of sections 5 and 6.
- **Weekly meeting lead, rotating ① → ② → ③ → ④:** prepares the agenda, takes short notes, updates the board and reminds everyone of upcoming milestones.

  | Week | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | Lead | ① | ② | ③ | ④ | ① | ② | ③ | ④ | ① | ② | ③ |

- **Report editor, a different person for each part:** sets up the report skeleton, writes the Introduction and Conclusion, merges the sections, harmonizes the style, exports the PDF and submits. Suggestion: ③ for Part I and ② for Part II, since their technical work finishes earlier in the last week of each part. This can be changed at the kickoff.
- **Last week of each part:** everyone proofreads 2 sections they did not write.
- **Reviews:** every task has one owner and one reviewer (via pull request). If someone is suddenly unavailable, the reviewer takes over.

---

## 4. Common setup (week 1)

### Tools
- **Git + GitHub:** private repo, GitHub Projects as the board, one issue per task.
- **Docker:** Windows machines need Docker Desktop + WSL2, because ClickHouse does not run natively on Windows.
- **ClickHouse:** pin one fixed version for both parts. Use the latest LTS (ClickHouse LTS releases are the xx.3 and xx.8 versions). Reason: support for correlated subqueries (needed by TPC-DS) and for the `UPDATE` statement (needed by TPC-DI) only arrived in 2025.
- **Python 3.11+** with `clickhouse-connect`, `pandas`, `matplotlib`, `duckdb`.
- **Report:** Overleaf (LaTeX). If the group is not comfortable with LaTeX, use Google Docs and export to PDF.

### Suggested repo layout
```
infoh419-clickhouse/
├── README.md              # how to reproduce (also used for the submission)
├── docker/                # docker-compose.yml, tpcds-kit build image, Java 8 image for DIGen
├── part1-tpcds/
│   ├── ddl/               # table creation + settings profile
│   ├── queries/           # the 99 adapted queries + CHANGES.md
│   ├── scripts/           # gen_data, load, harness
│   ├── results/           # raw result CSVs, with metadata
│   └── analysis/          # chart scripts/notebooks
├── part2-tpcdi/
│   ├── ddl/               # staging + warehouse
│   ├── etl/               # one SQL file per target table, historical / incremental
│   ├── scripts/           # gen_data, orchestrator, audit
│   ├── results/
│   └── analysis/
└── report/                # report sources for each part
```

### Conventions
- Never commit generated data (put `data/` in `.gitignore`); only commit the scripts that generate it.
- Every query change goes into `queries/CHANGES.md`: which query, what changed, why. This file becomes a report appendix.
- Every benchmark run saves a CSV with metadata: SF, ClickHouse version, settings, machine, time of the run.
- Work on a branch and open a pull request. Merge into `main` only after one review.

### Kickoff checklist (Mon 5 Oct)
- [ ] Pick the 4 roles.
- [ ] Pick the report editor for Part I and for Part II (two different people). Confirm the meeting lead rotation in section 3.
- [ ] Confirm the benchmark machine: CPU, cores, RAM, free disk (about 200 GB needed), OS.
- [ ] Create the group chat; confirm the Tuesday 16:00 meeting. The week 1 meeting lead (①) creates the repo and board.
- [ ] Split the queries as in section 3.
- [ ] Fill in the form on tpc.org to download the TPC-DS tools and the TPC-DI tools (get both now to avoid waiting later).
- [ ] Everyone installs Docker (and WSL2 on Windows) before the meeting on Tue 6 Oct.

---

## 5. Part I: TPC-DS

### Background
- TPC-DS has 24 tables (7 fact tables, 17 dimension tables). Data is generated with `dsdgen`; the SF roughly equals the size of the raw data in GB. The 99 queries are generated from templates with `dsqgen`, and each generation can use different parameters.
- ClickHouse now runs almost all 99 queries when an SQL-standard compatibility settings profile is enabled. The profile comes from `settings.json` in ClickHouse's official TPC-DS benchmark:
  ```
  data_type_default_nullable = 1
  join_use_nulls = 1
  group_by_use_nulls = 1
  union_default_mode = 'DISTINCT'
  intersect_default_mode = 'DISTINCT'
  joined_subquery_requires_alias = 0
  ```
- According to the README in the ClickHouse repo (updated June 2026), the remaining problem queries are:
  - Q17: returns `nan` instead of NULL.
  - Q35: runs out of memory.
  - Q47, Q57, Q58, Q75: need a small rewrite; the README provides the fixed versions.

  Re-check this list against the exact version we use.
- ClickHouse does not enforce PRIMARY KEY/FOREIGN KEY constraints. A ClickHouse "primary key" is really a sorting key with a sparse index, so the `ORDER BY` of each table is an important design decision. The report should explain these choices and link them to the Indexing chapter of the course.
- We can draw on the DDL (`init.sql`) and the query fixes in the ClickHouse repo, but we must understand every choice and cite the source in the report (ask the lecturer first, see section 8).

### Choosing the scale factors
- Pick a reference SF that is a multiple of 10, so that 0.1, 0.2 and 0.5 of it are whole numbers. Example: reference 100 gives the series 10, 20, 50, 100.
- With ≥ 32 GB RAM, try SF 100 first. Keep SF 100 if all three conditions hold:
  1. The load succeeds.
  2. There is enough disk space.
  3. A full run of the 99 queries finishes in an acceptable time (e.g. under 2 hours). Any query that runs out of memory must either be made to run by tuning settings, or its failure must be explainable.

  Otherwise fall back to 50, then 30.
- Decide the reference SF by Sun 18 Oct at the latest.

### Week 1 (5–11 Oct): Foundations

| Who | Tasks |
|---|---|
| ① | Write the `docker-compose` for ClickHouse. Write the image that builds tpcds-kit (`dsdgen`, `dsqgen`). Write the `gen_data <SF>` script (using `-PARALLEL`/`-CHILD` to generate in parallel) and the `load <SF>` script (loads the 24 tables and checks row counts). As week 1 meeting lead, also create the repo and board. |
| ② | Read the execution rules of the TPC-DS spec: load test, power test, throughput test, data maintenance, QphDS metric. Write a 1–2 page `docs/benchmark-protocol.md` (what to measure, how many repetitions, cold/warm, timeouts) for review at the 13 Oct meeting. Record the benchmark machine specs. With ①, generate and load SF 100 overnight as a trial. |
| ③ | Write the DDL for the 24 tables: map TPC-DS types to ClickHouse types, decide which columns are Nullable, the `ORDER BY` of each table (fact tables usually by the date column), and whether to partition. Write the settings profile. Record the reasoning in `docs/schema-notes.md` so it can be reused in the report. |
| ④ | Generate the qualification query set with `dsqgen -QUALIFY Y`, using a dialect with `LIMIT` (e.g. `netezza`). Build the DuckDB reference answers (see below). Write the result comparison script, allowing for rounding differences and ignoring row order when a query's `ORDER BY` is not strict enough. |
| Part I report editor | Set up the report skeleton. |
| Everyone | Install the environment and get SF 1 running on your own machine. |

**Reference answers (built by ④):** the most reliable way is to load the same SF 1 `.dat` files into DuckDB (`pip install duckdb`), run the same original queries, and store the results as the reference. We can also cross-check against:
- The answer sets shipped with the official TPC-DS kit (the `answer_sets` folder, if present in the download).
- DuckDB's `tpcds_answers()` function. Note that it only has answers for SF 1 and 10, with fixed query parameters.

**Done when:**
- A single command generates and loads SF 1 on at least 2 machines.
- We know how long SF 100 takes to load and how much disk it uses.
- Reference answers exist for SF 1.

### Week 2 (12–18 Oct): 99 correct queries + harness

| Who | Tasks |
|---|---|
| Everyone | Run your 25 queries at SF 1, fix syntax or semantic errors, and compare against the reference answers with ④'s script. Log every change in `CHANGES.md`. |
| ④ | Keep a status table of the 99 queries (matching / fixed / still failing). Help when results differ from the reference. Generate the query streams for the throughput test (`dsqgen -STREAMS`). |
| ③ | Fix the hard queries (Q17, Q35, Q47, Q57, Q58, Q75) and the memory-hungry ones. Adjust the settings profile if needed. |
| ② | Write the Python harness with two modes: power (sequential, repeated N times) and throughput (S streams in parallel). For each query, record wall time, server-side time, rows and bytes read, peak memory (from `system.query_log`), and status OK/error/timeout. Output a CSV with metadata. Draft the Methodology section from the protocol. |
| ① | Write the cold-run reset script (restart ClickHouse, drop the OS page cache, run `SYSTEM DROP … CACHE`) for the harness to call. Prepare gen + load for the whole SF series. |
| ② + ① | At the end of the week, run all 99 queries once at SF 100, then **decide the reference SF**. |

**Done when:** each of the 99 queries either matches the reference answer at SF 1 or has a documented failure with its reason. The harness outputs a CSV. The reference SF is decided.

**Decision at the end of week 2:** if there is time left, ③ and ① implement data maintenance. If not, the report states clearly that it was not done.

### Week 3 (19–25 Oct): Measurements

| Who | Tasks |
|---|---|
| ① | On the benchmark machine, for each SF in turn: generate the data, load it, then delete the raw files to save disk. Record load times (load test) and on-disk size before/after compression (from `system.parts`). |
| ② | Run the protocol at all 4 SFs. Power test: the 99 queries sequentially, 1 cold run + 3 warm runs. Throughput test: e.g. 4 streams (check the minimum number of streams required by the spec). Run overnight and save the raw CSVs in `results/`. |
| ③ | Handle failing or abnormal queries at large SFs: try another `join_algorithm`, let GROUP BY/JOIN spill to disk, tune `max_memory_usage`. |
| ④ | Write the analysis scripts and charts as soon as the first results arrive. Use `EXPLAIN` on the slow queries. |
| Everyone | Write your report sections (see the "who writes what" table below). |

**Done when:** result CSVs exist for all 4 SFs, and report sections 2 to 6 are drafted.

### Week 4 (26 Oct–1 Nov): Analysis and submission

| Who | Tasks |
|---|---|
| ④ | Finalize the charts and analysis: load time per SF; time per query (log scale); scaling curves (does time grow linearly with SF?); power vs throughput; slowest queries. |
| ③ | With ④, explain anomalies using `EXPLAIN` and `system.query_log` (which queries scale badly and why); write the Discussion section. |
| ② | Compute a simplified QphDS-style metric, stating the formula and the deviations from the spec. Run extra measurements if needed. |
| ① | Package the zip: a reproduction README (machine requirements, steps, expected time and disk usage), all scripts, DDL, queries, harness and results. **Ask another member to rebuild everything from scratch using only the README**, and fill any gaps. |
| Part I report editor | Merge the report, write the Introduction and Conclusion, harmonize the style, add references and appendices, export the PDF, submit. |
| Everyone | Proofread 2 sections you did not write. |

**Milestones:** full draft on Wed 28 Oct → freeze on Fri 30 Oct → submit on Sat 31 Oct (deadline Sun 1 Nov).

### Part I report outline and who writes what

| Section | Writer |
|---|---|
| 1. Introduction | Part I report editor |
| 2. TPC-DS overview | ② |
| 3. ClickHouse overview (link to course concepts: star/snowflake schemas, indexing, materialization) | ③ |
| 4. Experimental setup (machine, versions, settings, SF choice) | ② |
| 5. Implementation: data generation and loading | ① |
| 5. Implementation: schema and settings | ③ |
| 5. Implementation: query generation, fixes and validation | ④ |
| 6. Benchmark methodology | ② |
| 7. Results | ④ (charts, analysis), ② (metric) |
| 8. Discussion (strengths/weaknesses, failing queries, deviations from the spec) | ③ and ④ |
| 9. Conclusion | Part I report editor |
| Appendix: list of modified queries | ④ |
| Appendix: reproduction guide | ① |

---

## 6. Part II: TPC-DI

### Background
- TPC-DI models the ETL process of a brokerage firm. The sources come in many formats: CSV, `|`-delimited files, XML (`CustomerMgmt.xml`) and fixed-width (the `FINWIRE*` files).
- The data comes in 3 batches. Batch1 is the historical load. Batch2 and Batch3 are incremental updates, made of CDC files with I/U flags.
- Target tables: the Dim\* and Fact\* tables, plus Financial, Prospect, the reference tables, DImessages and the audit table used for validation.
- Data is generated with `java -jar DIGen.jar -sf <SF> -o <directory>`. It is an old, single-threaded tool. Other implementations all run it on Java 8, so we also use Java 8 in Docker to be safe. Size: SF 10 ≈ 1 GB, SF 100 ≈ 10 GB of raw data.
- **Pain points on ClickHouse:**
  - ClickHouse cannot read XML (XML is an output-only format). A small Python script must convert `CustomerMgmt.xml` to CSV/JSON before loading.
  - FINWIRE: load whole raw lines (`LineAsString` format), then cut them into columns with `substring`.
  - ClickHouse has no SERIAL/IDENTITY, so surrogate keys must be generated with `row_number()` plus the current maximum.
  - Since version 25.7 there is a lightweight `UPDATE … SET … WHERE` statement. Avoid `ALTER TABLE … UPDATE`: it is a mutation and very heavy.
- **Helpful features:** `ASOF JOIN` is a natural fit for finding the dimension version valid at the time of a transaction (SCD2). Window functions can compute EndDate/IsCurrent and the 52-week window of FactMarketHistory.

### Choosing the ETL architecture (decide by Sun 8 Nov)

| Option | Pros | Cons |
|---|---|---|
| **A. ELT inside ClickHouse (recommended):** load raw files into staging tables, transform with SQL files (`INSERT … SELECT`), and use a Python script that runs the steps in order and times them | Single engine, continuous with Part I. Fast, and easy to time each step. Gives the report plenty to discuss about ClickHouse. | SCD2/UPDATE logic must be written carefully in SQL. XML still needs Python. |
| B. dbt + the dbt-clickhouse adapter | Dependency management, tests and documentation out of the box. | Extra learning. Incremental models/snapshots on ClickHouse come with many caveats; risky with only 7 weeks. |
| C. Python (pandas/Polars) for the ETL, ClickHouse only as storage | Flexible parsing and logic. | Slow and memory-hungry at large SFs. The transformations live outside the DW, so there is little to say about ClickHouse. |

### SCD2 and update strategy (③ builds a prototype in week 5)
- **Historical load:** compute EffectiveDate, EndDate and IsCurrent with window functions (`lead(...) OVER (PARTITION BY natural key ORDER BY date)`). This step only needs INSERT, no UPDATE.
- **Incremental:** pick one of three approaches, trying DimAccount first:
  1. Rebuild the affected dimension into a new table, then `EXCHANGE TABLES`. Simple and easy to get right; suits medium-sized dimensions.
  2. Use a lightweight `UPDATE` to close the old version, then INSERT the new version.
  3. Use `ReplacingMergeTree` with a version column and read with `FINAL`.
- **Suggestion:** for medium-sized dimensions, start with approach 1 since it is the easiest to get right. Measure, and only switch to approach 2 if it is too slow. DimTrade is very large, so use approach 2 or 3 from the start.

### Table clusters

| Cluster | Target tables | Main sources | Role |
|---|---|---|---|
| A | DimDate, DimTime, Industry, StatusType, TaxRate, TradeType, DimBroker, DimCompany, DimSecurity, Financial | Date.txt, Time.txt, reference files, HR.csv, FINWIRE | ① |
| B | DimCustomer, DimAccount, Prospect | CustomerMgmt.xml, Prospect.csv; Customer.txt and Account.txt in batches 2–3 | ③ |
| C | DimTrade, FactCashBalances, FactHoldings | Trade.txt, TradeHistory.txt, CashTransaction.txt, HoldingHistory.txt | ② |
| D | FactWatches, FactMarketHistory, DImessages, audit | WatchHistory.txt, DailyMarket.txt, the `*_audit.csv` files | ④ |

**Dependency order:**
- Cluster A comes first: reference tables, DimBroker, DimCompany, DimSecurity, Financial.
- Cluster B needs cluster A: DimCustomer, then DimAccount.
- Cluster C needs cluster B: DimTrade, then the fact tables.
- Cluster D needs DimSecurity, DimCompany, Financial (from cluster A) and DimCustomer (from cluster B).

So the dimensions of clusters A and B must be done by Sun 15 Nov. Meanwhile, clusters C and D work on parsing/staging and write their logic against dummy data.

### Week 5 (2–8 Nov): Understand the spec, settle the design

| Who | Tasks |
|---|---|
| ① | Run DIGen in Docker (Java 8) and generate SF 10 as development data. Write loaders that bring each file type into staging: CSV, `|`-delimited files, XML → CSV with Python, FINWIRE as raw lines. Draft the architecture diagram. |
| ② | Read the execution rules and metric (TPC_DI_RPS) in the spec. Plan the measurements: timing for each phase and step. |
| ③ | Write the staging and DW DDL. Prototype SCD2 on DimAccount and propose the update strategy. |
| ④ | Read the audit part of the spec and the audit script shipped with the kit, and plan the port to ClickHouse. Read the rules for writing DImessages. |
| Part II report editor | Set up the Part II report skeleton. |
| Everyone | Read the source description and transformation rules for your cluster. Review the Dimension Changes (dw04) and ETL (dw05) slides; this helps both the project and the exam. |

**Done when:**
- SF 10 data is loaded into staging.
- The architecture and SCD2 strategy are decided (30-minute online meeting before Sun 8 Nov).
- Table and column names match the spec exactly, so the audit script runs without many changes.

### Weeks 6–7 (9–22 Nov): Historical load

| Who | Tasks |
|---|---|
| Everyone | One SQL file per target table for the historical load. Run it at SF 10, check row counts and spot-check a few records against the spec rules. Write the source → target mapping for your cluster, for use in the report. |
| ① | Write the Python orchestrator: runs the steps in dependency order and records row counts. |
| ② | With ①, add per-step timing to the orchestrator. |
| ③ | Help the other clusters apply the agreed SCD2 and surrogate key strategy. |
| ④ | Port the audit script to ClickHouse syntax; write DImessages. |
| ② + ① | At the end of week 7, try the historical load at SF 100 on the benchmark machine to find out early whether that reference SF is feasible. |

**Milestones:** the dimensions of clusters A and B are done by Sun 15 Nov. By Sun 22 Nov the whole historical load runs with a single command at SF 10.

### Weeks 8–9 (23 Nov–6 Dec): Incremental loads and validation

| Who | Tasks |
|---|---|
| Everyone | Write the incremental logic for your tables: handle CDC I/U, SCD2 for DimCustomer/DimAccount, status updates for DimTrade, appending rows to the fact tables. |
| ① | Make the orchestrator run the full HL → IU1 → IU2 sequence, with a check between batches. |
| ③ | Help the clusters with SCD2 in the incremental loads (close the old version, open the new one). |
| ④ | Run the audit after each batch. Hand any failure back to the table's owner. |
| ② + ① | Test large SFs on the benchmark machine to **decide the TPC-DI reference SF by Sun 6 Dec** (a multiple of 10; try SF 100 first). Then generate the data for the whole SF series right away, because DIGen is single-threaded and very slow. |

**Done when:** the audit passes at SF 10 (or every remaining failure is explained), and the whole pipeline runs with a single command.

### Week 10 (7–13 Dec): Measurements

| Who | Tasks |
|---|---|
| ② | Run the pipeline at all 4 SFs (2–3 repetitions if time allows). Record the time of each phase (HL, IU1, IU2) and each step, plus row counts. Compute throughput and TPC_DI_RPS, stating the deviations from the spec. |
| ① | Prepare the data, free up disk space, support the overnight runs. |
| ④ | Write the analysis scripts and charts as soon as results arrive. |
| Everyone | Write your report sections (see the "who writes what" table below). |

### Week 11 (14–20 Dec): Analysis and submission

| Who | Tasks |
|---|---|
| ④ | Finalize the charts and analysis: time per phase/step and per SF, showing which steps dominate. |
| ③ | With ④, write the Discussion: is ClickHouse a good fit for ETL (UPDATE, SCD2, XML)? |
| ② | Finalize the metric and the numbers in the Results section. |
| ① | Package the zip and ask another member to rebuild everything from scratch using only the README. |
| Part II report editor | Merge the report, write the Introduction and Conclusion, harmonize the style, export the PDF, submit. |
| Everyone | Proofread 2 sections you did not write. |

**Milestones:** full draft on Wed 16 Dec → freeze on Fri 18 Dec → submit before Mon 21 Dec. 21–24 Dec is buffer.

### Part II report outline and who writes what

| Section | Writer |
|---|---|
| 1. Introduction | Part II report editor |
| 2. TPC-DI overview (scenario, sources, DW model, phases, metric) | ③ |
| 3. Architecture (diagram, tools, rationale) | ① |
| 4. Implementation: staging, loaders, orchestration | ① |
| 4. Implementation: DW schema, SCD2, surrogate keys | ③ |
| 4. Implementation: transformation rules of each cluster | Each cluster's owner |
| 5. Validation (audit results, DImessages) | ④ |
| 6. Benchmark setup & methodology | ② |
| 7. Results | ④ (charts, analysis), ② (metric) |
| 8. Discussion (is ClickHouse a good fit for ETL?) | ③ and ④ |
| 9. Conclusion | Part II report editor |
| Appendix: reproduction guide | ① |

---

## 7. Benchmark methodology checklist (both parts)

- [ ] Every measurement runs on the same machine, with the same ClickHouse version and the same settings. Record CPU, cores, RAM, disk type, OS and software versions.
- [ ] Laptops must be plugged in, in high-performance mode, with other apps closed. Avoid running while Windows Update or the antivirus is scanning.
- [ ] If the benchmark machine runs Windows: run ClickHouse in WSL2/Docker and keep the data inside the WSL2 filesystem. Do not put it on `/mnt/c`: I/O there is much slower.
- [ ] After loading, ClickHouse keeps merging parts in the background. Either wait until the merges are done (`system.merges` is empty), or run `OPTIMIZE TABLE … FINAL` and count it in the load time. Pick one and state it in the report.
- [ ] Define cold and warm clearly. Cold: restart ClickHouse, drop the OS page cache, run the `SYSTEM DROP … CACHE` commands. Warm: the runs that follow.
- [ ] Keep the query cache off (`use_query_cache = 0`, off by default) and say so in the report.
- [ ] Repeat at least 3 times. Report the median with min/max or the standard deviation.
- [ ] Set a timeout and a memory limit per query. A failure or timeout is also a result: report it, do not hide it.
- [ ] Check correctness before measuring. Timings of a query that returns wrong results are worthless.
- [ ] Save raw results (CSV) with metadata. Charts must be generated by scripts, never edited by hand.
- [ ] State every deviation from the spec. Call the results "derived from TPC-DS/TPC-DI", never official TPC results (this is required by the TPC fair use policy).

---

## 8. Questions to ask the lecturer early (by email or after the lecture)

1. Is there a page limit or a template for the report?
2. Is there a presentation or demo?
3. Is data maintenance mandatory for Part I, and must the full QphDS metric be computed?
4. How do we submit? Is there a size limit for the zip? (We plan to submit only the data generation scripts, not the data.)
5. May we draw on the TPC-DS DDL and query fixes published in the ClickHouse repo, as long as we cite them?

---

## 9. Risks and mitigations

| Risk | Prevention / response |
|---|---|
| `dsdgen`/`dsqgen` fail to build on Windows | Build in Docker or WSL2. |
| Queries return wrong results because of NULL semantics | Use the settings profile from section 5, and compare against the reference answers at SF 1 before measuring. |
| Out of memory at large SFs (Q35 is a known case) | Change `join_algorithm`, allow spilling to disk, tune `max_memory_usage`. If it still fails, report it or lower the reference SF. |
| Running out of disk | Process one SF at a time: generate → load → delete raw files. Check free disk space in week 1. |
| Noisy measurements | Follow the checklist in section 7. |
| DIGen fails on recent Java | Use Java 8 in Docker. |
| XML and fixed-width sources | Python for XML, `substring` on raw lines for FINWIRE. |
| SCD2 or UPDATE gets too complex | Prototype in week 5. Keep "rebuild + `EXCHANGE TABLES`" as the fallback. |
| Clusters C and D blocked waiting for dimensions | Dimension milestone on 15 Nov. Meanwhile, work on parsing/staging with dummy data. |
| The lecturer cannot rebuild our setup | Pin versions, use Docker, and rebuild from a clean clone on another machine before submitting. |
| Someone is busy or away in December | Internal freeze on 18 Dec, buffer 21–24 Dec. Every task has a reviewer who can take over. |
| The project eats into exam preparation (the exam is 70%) | In the discussion sections, link our findings to the course chapters (indexing, materialization, SCD, ETL), so that the project doubles as exam revision. |

---

## 10. References

- Course page: https://cs.ulb.ac.be/public/teaching/infoh419 (slides dw04 Dimension Changes, dw05 ETL, dw06 View Materialization, dw07 Indexing)
- TPC specs and tools: https://www.tpc.org/tpc_documents_current_versions/current_specifications5.asp (TPC-DS: https://www.tpc.org/tpcds/, TPC-DI: https://www.tpc.org/tpcdi/)
- ClickHouse TPC-DS docs: https://clickhouse.com/docs/get-started/sample-datasets/tpcds
- ClickHouse repo, TPC-DS benchmark (`init.sql`, `settings.json`, README listing the problem queries, the 99 queries): https://github.com/ClickHouse/ClickHouse/tree/master/tests/benchmarks/tpc-ds
- tpcds-kit (the fork used by the ClickHouse docs): https://github.com/gregrahn/tpcds-kit
- ClickHouse UPDATE statement: https://clickhouse.com/docs/reference/statements/update, and the blog post https://clickhouse.com/blog/updates-in-clickhouse-2-sql-style-updates
- DuckDB TPC-DS extension: https://duckdb.org/docs/current/core_extensions/tpcds
- databricks-tpc-di (reference for the TPC-DI structure, DIGen usage, sizes per SF): https://github.com/shannon-barrow/databricks-tpc-di
