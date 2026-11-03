# INFO-H-419 Data Warehouses: TPC-DS and TPC-DI on ClickHouse

**Team:** Bao Anh Tran, Anabelle Meli, Cyril Stembert, Paula Ventura
**Course:** INFO-H-419 Data Warehouses (ULB), Prof. Esteban Zimányi

Results in this repository are *derived from* TPC-DS and TPC-DI. They are not official TPC results.

Part I (TPC-DS) is complete: the steps below rebuild it from scratch, from the data generation to the
charts of the report. Part II (TPC-DI) has not started yet.

## Quick start: one command

```bash
git clone https://github.com/cyyr1l/info-h419-clickhouse.git
cd info-h419-clickhouse
./run.sh          # the whole benchmark: check at SF 1, then SF 12, 20, 30 and 50, then the charts (about 3 hours)
```

`./run.sh 1` does a quick run at SF 1 only (about 10 minutes). `run.sh` runs the steps of
[Part I](#part-i-tpc-ds) below in order and stops at the first error with a message. It needs Docker and
Python 3.10 or later (see [Requirements](#requirements)): everything else, the TPC-DS tools included, is in
the repository or is downloaded by Docker. Each campaign writes its results to
`part1-tpcds/results/sf<SF>/<run_id>/`, and the log of the run goes to `data/run-<time>.log`. On Windows,
run it in a WSL2 terminal.

## Repository layout

```
info-h419-clickhouse/
├── README.md                  # this file: how to reproduce
├── run.sh                     # the whole Part I benchmark in one command
├── docker/
│   ├── docker-compose.yml     # ClickHouse 26.8.24.9 server + the TPC-DS tools image
│   └── tpcds-kit/             # Dockerfile that builds dsdgen/dsqgen from the TPC zip, rowcounts.c helper
├── docs/                      # benchmark protocol, schema notes, project roadmap
├── part1-tpcds/
│   ├── ddl/schema.sql         # the 24 tables (MergeTree)
│   ├── settings.json          # settings profile sent with every query
│   ├── queries/               # our query templates, original queries, CHANGES.md (every query change)
│   ├── reference/             # reference answers at SF 1 (DuckDB), used to validate the queries
│   ├── scripts/               # gen_data, load, gen_queries, harness (benchmark driver), compare, tests
│   ├── results/               # raw results of our runs (SF 12, 20, 30, 50), one folder per run
│   ├── analysis/              # charts and tables of the report, EXPLAIN of the slowest queries
│   └── query_status.md        # validation status of the 99 queries
├── part2-tpcdi/               # Part II (not started)
├── report/                    # output folder of the charts (report/part1/figures/); the reports are submitted as PDF
└── tools/                     # TPC-DS Tools v4.0.0 (TPC licence, see tools/README.md)
```

Generated files go to `data/` (raw data, generated queries, validation output, logs), which is not versioned.

## Requirements

| | Check at SF 1 | Our benchmark (SF 12 to 50) |
|---|---|---|
| Processor | any | 16 threads (Intel Core i5-12600KF) |
| Memory | 8 GB | 32 GB, of which 24 GB for Docker/WSL2 |
| Free disk | about 5 GB | about 160 GB for SF 50 (see [time and disk](#expected-time-and-disk-use)), on an SSD |
| Time | about 10 minutes | about 3 hours for the four scale factors |

- **Docker** with Docker Compose v2: Docker Desktop on Windows and macOS, Docker Engine on Linux.
  ClickHouse and the TPC-DS tools run in containers, so no compiler and no local ClickHouse are needed.
  The first run downloads the images (ClickHouse, Debian for the TPC-DS tools, Alpine for the cold runs),
  so it needs internet access.
- **Python 3.10 or later** (we used 3.12). The benchmark scripts only use the standard library.
  Two optional steps need packages: `pandas` and `matplotlib` for the charts (step 6), `duckdb` to rebuild
  the reference answers, which are already in the repository.
- **Windows:** run every command in a WSL2 terminal (Ubuntu), with the repository inside the WSL2 file
  system (e.g. `~/info-h419-clickhouse`), not on a Windows drive (`C:\` or `/mnt/c`): from a Windows drive,
  data generation is about 30 times slower. In Docker Desktop, enable the WSL integration for your
  distribution (Settings → Resources → WSL integration). WSL2 gets only half of the RAM by default; for
  the benchmark, raise it in `%UserProfile%\.wslconfig`, then run `wsl --shutdown` and restart Docker Desktop:
  ```
  [wsl2]
  memory=24GB
  processors=16
  ```
- **macOS:** in Docker Desktop, Settings → Resources, raise the memory, the CPUs and the disk size limit.

## Part I: TPC-DS

Run every command from the root of the repository.

### 1. The TPC-DS tools

**THE TPC SOFTWARE IS AVAILABLE WITHOUT CHARGE FROM TPC.** The TPC-DS Tools v4.0.0 are included in
`tools/DSGen-software-code-4.0.0/`, unmodified, under clause 9 of the TPC licence (its full text is in
`tools/DSGen-software-code-4.0.0/EULA.txt`; see [`tools/README.md`](tools/README.md)). There is nothing to
download. The scripts build `dsdgen` and `dsqgen` from this folder in a Docker image the first time they
need them (about 1 to 2 minutes).

### 2. Start ClickHouse

```bash
mkdir -p data                     # before the first start, otherwise Docker creates data/ as root
docker compose -f docker/docker-compose.yml up -d --wait     # returns once the server is "healthy"
docker compose -f docker/docker-compose.yml exec clickhouse clickhouse-client --password infoh419 --query "SELECT version()"
```

The last command must print `26.8.24.9`, the version pinned in `docker/docker-compose.yml`. ClickHouse
only listens on 127.0.0.1 (ports 8123 and 9000) and keeps its databases in a Docker volume
(`docker compose -f docker/docker-compose.yml down -v` deletes them). The generated data in `data/` is
mounted read-only into the container, so that ClickHouse reads the files itself during the load.

### 3. Check the setup at SF 1 (about 10 minutes)

Generate and load SF 1, then run the 99 queries once and compare their results with the reference
answers:

```bash
python3 part1-tpcds/scripts/gen_data.py --sf 1      # data/tpcds/sf1/, then checks the 24 tables
python3 part1-tpcds/scripts/load.py --sf 1          # database tpcds_sf1, then checks the row counts
python3 part1-tpcds/scripts/gen_queries.py validation
python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/validation --out data/validation/sf1
python3 part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1 data/validation/sf1
```

`gen_data.py` and `load.py` end with an `OK` line, or stop with an error that names the table at fault.
`compare.py` prints one status per SQL statement (103 for the 99 queries): all of them must be `OK`,
`OK (different order)` or `OK (both empty)`. The reference answers were computed by DuckDB on the same
data (report, Section 5.3).

Ten reference results are empty with these parameters, which is a weak check. The templates concerned are
also checked with the official qualification parameters, with which they return rows:

```bash
python3 part1-tpcds/scripts/gen_qualify.py
python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/qualify --out data/validation/sf1_qualify
python3 part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1_qualify data/validation/sf1_qualify
```

The details, and how to rebuild the reference answers, are in
[`part1-tpcds/scripts/README_validation.md`](part1-tpcds/scripts/README_validation.md).

### 4. Benchmark one scale factor

```bash
N=12
python3 part1-tpcds/scripts/gen_data.py --sf $N
python3 part1-tpcds/scripts/gen_queries.py streams --sf $N    # data/queries/sf12/query_0.sql … query_4.sql
python3 part1-tpcds/scripts/harness.py campaign --sf $N --streams-dir data/queries/sf$N \
        --load-cmd "python3 part1-tpcds/scripts/load.py --sf $N"
```

The `campaign` command runs the whole protocol of the report (Section 6) for one scale factor:

1. the load test: `load.py` followed by `OPTIMIZE TABLE … FINAL` on every table, timed as T_Load;
2. the power test: stream 0, the 99 queries one after the other (T_Power);
3. the throughput test: streams 1 to 4 at the same time (T_TT1);
4. one cold power run (ClickHouse restarted and the Linux page cache dropped), then three warm power runs.

A campaign takes about T_Load + 9 × T_Power. The results go to `part1-tpcds/results/sf<N>/<run_id>/`: one
CSV file per test with one row per SQL statement, `load.csv`, `summary.json` (T_Load, T_Power, T_TT1,
failures, simplified metric) and `environment.json` (machine, versions, settings, SHA-256 of the query
files). [`part1-tpcds/scripts/README_harness.md`](part1-tpcds/scripts/README_harness.md) describes the
files and the single commands (`load`, `power`, `throughput`).

For a measured run, close other applications, keep the computer on mains power in its highest
performance mode, and stop every other container: `docker ps` must list only `infoh419-clickhouse`.
ClickHouse sets its memory limit from the free memory, so another container would change the results;
the harness warns if one is running.

### 5. Our series: SF 12, 20, 30 and 50

The report uses SF 50 as the reference and SF 12, 20 and 30 as the smaller scale factors (report,
Section 4.3). To rerun all four, from the smallest to the largest:

```bash
for N in 12 20 30 50; do
  python3 part1-tpcds/scripts/gen_data.py --sf $N
  python3 part1-tpcds/scripts/gen_queries.py streams --sf $N
  python3 part1-tpcds/scripts/harness.py campaign --sf $N --streams-dir data/queries/sf$N \
          --load-cmd "python3 part1-tpcds/scripts/load.py --sf $N"
  rm data/tpcds/sf$N/*.dat          # free the disk; keep manifest.json
  docker compose -f docker/docker-compose.yml exec clickhouse \
          clickhouse-client --password infoh419 --query "DROP DATABASE tpcds_sf$N"
done
```

The last two commands of the loop free the disk. The raw files can be deleted once a campaign is over,
because `dsdgen` is deterministic: `gen_data.py` regenerates exactly the same files. Keep the database of
SF 50 if you want to run `explain_queries.py` afterwards (step 6). Our own results are in
`part1-tpcds/results/` (one run per scale factor); a new run gets a new `<run_id>` folder next to them.

#### Expected time and disk use

Measured on our machine, with the times as recorded by the harness (its clock ran about 8% fast, see the
report, Section 4.1):

| SF | Generation | Raw files | T_Load | Database on disk | T_Power | Whole campaign |
|---|---|---|---|---|---|---|
| 1 | 37 s | 1.2 GB | 12 s | 0.7 GB | 15 s | 2.6 min |
| 12 | 2.3 min | 11.2 GB | 1.3 min | 7.0 GB | 1.6 min | 13 min |
| 20 | 1.8 min | 18.7 GB | 3.0 min | 11.7 GB | 3.1 min | 24 min |
| 30 | 3.2 min | 28.2 GB | 7.1 min | 17.7 GB | 5.7 min | 47 min |
| 50 | 4.0 min | 47.4 GB | 13.5 min | 30.0 GB | 11.0 min | 84 min |

During the load, `OPTIMIZE TABLE … FINAL` writes a new copy of every table, and ClickHouse keeps the old
parts for a few minutes, so the disk use peaks above the final database size. On Windows, the virtual disk
of Docker grows by this peak and does not give the space back by itself: during the SF 50 campaign, it grew
by about 113 GB. With the 47 GB of raw files, plan about 160 GB of free space for SF 50.

Memory: ClickHouse may use 90% of the memory it sees, about 20 GiB with 24 GB given to WSL2. The largest
query (Q69) needs 15.3 GiB alone at SF 50, and three of its executions in the throughput tests at SF 30 and
SF 50 ran out of memory (report, Section 7.5). With less memory, choose smaller scale factors.

### 6. Charts and tables of the report

The figures and tables of the report's Results section are generated from the results folders, without
ClickHouse:

```bash
python3 -m venv .venv             # on Debian/Ubuntu, this needs: sudo apt install python3-venv
.venv/bin/pip install pandas matplotlib
.venv/bin/python part1-tpcds/analysis/make_charts.py      # writes report/part1/figures/
```

It takes the latest run of every scale factor in `part1-tpcds/results/`. To get exactly our figures after
other runs, move the folders of other scale factors out of `part1-tpcds/results/` (e.g. `sf1/` after
`./run.sh 1`), and if you ran SF 12 to 50 again, pick our runs with `--run SF=RUN_ID` (e.g.
`--run 12=20261026-193856`). [`part1-tpcds/analysis/README.md`](part1-tpcds/analysis/README.md) explains
each chart and the rules used.

With a scale factor loaded and its streams generated, `explain_queries.py` saves the execution plans and
the `system.query_log` values of the slowest queries (report, Section 8), in `data/explain/sf<N>/`:

```bash
python3 part1-tpcds/analysis/explain_queries.py --sf 50
```

### 7. Tests

```bash
python3 -m unittest part1-tpcds/scripts/test_harness.py part1-tpcds/scripts/test_compare.py
```

The tests that need ClickHouse are skipped when no server answers on `localhost:8123`.

### Common problems

| Symptom | Cause and fix |
|---|---|
| `docker compose build tpcds-kit failed` | The first build downloads Debian packages, so it needs internet access; `tools/DSGen-software-code-4.0.0/` must also be complete (step 1). |
| `cannot reach ClickHouse at http://localhost:8123/` | ClickHouse is not running: `docker compose -f docker/docker-compose.yml up -d --wait`. |
| `load.py` finds no files although `gen_data.py` succeeded | The ClickHouse container was created from another copy of the repository, so it mounts another `data/` folder. Recreate it: `docker compose -f docker/docker-compose.yml up -d --force-recreate clickhouse`. |
| `manifest.json not found` | Run `gen_data.py --sf N` before `load.py --sf N`. |
| `PermissionError` on `data/…` from `gen_data.py` | ClickHouse was started before `data/` existed, so Docker created it as root. Stop ClickHouse (`docker compose -f docker/docker-compose.yml stop`), delete the empty folder (`rmdir data`), then run step 2 again from `mkdir -p data`. |
| `dsdgen` cannot open its output files (Linux) | The tools container writes as user 1000. If your user id differs, run `export UID; export GID=$(id -g)` first. |
| Not enough disk during `gen_data.py` or the load | Free disk space, e.g. delete the raw files and the database of a scale factor already measured (step 5). |
| Very slow generation on Windows | The repository is on a Windows drive: clone or unzip it inside the WSL2 file system. |
| `docker: command not found` in WSL2 | Docker Desktop is not running, or its WSL integration is off for this distribution. |
| Queries fail with a memory error (code 241) at large scale factors | Docker or WSL2 has too little memory, or other containers run and lower ClickHouse's limit: stop them. |

### Further documentation

- [`docs/benchmark-protocol.md`](docs/benchmark-protocol.md): what we measure and how (tests, cold and warm runs, timeouts).
- [`docs/schema-notes.md`](docs/schema-notes.md): data types, nullability and sorting keys of the schema.
- [`part1-tpcds/queries/CHANGES.md`](part1-tpcds/queries/CHANGES.md): every change to a TPC-DS query, with its reason.
- [`part1-tpcds/query_status.md`](part1-tpcds/query_status.md): validation status of the 99 queries.

## Part II: TPC-DI

Not started yet. It will use the same ClickHouse server and the TPC-DI Tools v1.1.0 (DIGen), also in `tools/`.

## Team conventions

- Never commit generated data; only commit the scripts that generate it.
- Every query change goes into `part1-tpcds/queries/CHANGES.md`.
- Every benchmark run saves its results with metadata (SF, ClickHouse version, settings, machine, time of the run).
- Work on a branch and open a pull request. Merge into `main` only after one review.
