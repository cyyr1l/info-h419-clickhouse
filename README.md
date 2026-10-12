# INFO-H-419 Data Warehouses: TPC-DS and TPC-DI on ClickHouse

**Team:** Bao Anh Tran, Anabelle Meli, Cyril Stembert, Paula Ventura
**Course:** INFO-H-419 Data Warehouses (ULB), Prof. Esteban Zimányi

Results in this repository are *derived from* TPC-DS and TPC-DI. They are not official TPC results.

## Repository layout

```
infoh419-clickhouse/
├── README.md              # how to reproduce (also used for the submission)
├── docker/                # docker-compose.yml, tpcds-kit build image, Java 8 image for DIGen
├── docs/                  # internal notes (benchmark protocol, schema notes)
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
    ├── part1/
    └── part2/
```

## Prerequisites

- Docker (Docker Desktop + WSL2 on Windows)
- Python 3.11+ with `clickhouse-connect`, `pandas`, `matplotlib`, `duckdb`
- ClickHouse version: *TODO: pin the LTS version used*

## Getting the TPC tools

The TPC tools are **not** included in this repository (TPC licence). Download them from
https://www.tpc.org/tpc_documents_current_versions/current_specifications5.asp :

- TPC-DS Tools (version: *TODO*)
- TPC-DI Tools v1.1.0

Place the zips in `tools/` (ignored by Git).

## How to reproduce

### Part I: TPC-DS

*TODO*

### Part II: TPC-DI

*TODO*

## Team conventions

- Never commit generated data; only commit the scripts that generate it.
- Every query change goes into `part1-tpcds/queries/CHANGES.md`.
- Every benchmark run saves a CSV with metadata (SF, ClickHouse version, settings, machine, time of the run).
- Work on a branch and open a pull request. Merge into `main` only after one review.
