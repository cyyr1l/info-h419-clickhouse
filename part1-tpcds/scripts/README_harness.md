# Benchmark harness (role ②)

`harness.py` runs the TPC-DS queries on ClickHouse and records the timings, following
[`docs/benchmark-protocol.md`](../../docs/benchmark-protocol.md). It only needs Python 3.10+ (standard
library) and the ClickHouse container (`cd docker && docker compose up -d`). It sends every query with the
settings profile [`part1-tpcds/settings.json`](../settings.json).

## Validate your queries (everyone)

Run your queries once on SF 1 and save each result as CSV, named like the reference answers:

```bash
python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/validation --only 26-50 --out data/validation/sf1
python3 part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1 data/validation/sf1
```

`--queries` takes a folder of `qNN.sql` files, single files, or stream files. The database defaults to
`tpcds_sf<SF>` (`--database` to change it). Queries must already be ClickHouse-ready: the harness runs them
exactly as given (protocol, section 7).

## Benchmark (role ②, on the benchmark machine)

One command runs the whole protocol for one SF: load test (optional), power test, throughput test, then
1 cold and 3 warm power runs.

```bash
python3 part1-tpcds/scripts/harness.py campaign --sf 10 --streams-dir <dir with query_0.sql … query_4.sql> \
        --load-cmd "<command that creates and loads tpcds_sf10>"
```

The single steps also exist: `load`, `power` (`--cold`, `--repeat`, `--test`) and `throughput`. Use
`--run-id` to put several commands in the same run folder. `python3 part1-tpcds/scripts/harness.py <command> -h`
lists all options.

Results go to `part1-tpcds/results/sf<SF>/<run_id>/`:

| File | Content |
|---|---|
| `power.csv`, `throughput.csv`, `power_cold.csv`, `power_warm.csv` | one row per SQL statement: timings, `system.query_log` values, status (`ok`, `error`, `timeout`, `memory`) |
| `load.csv` | one row per table after `OPTIMIZE … FINAL`: rows, parts, sizes, optimize time |
| `summary.json` | T_Load, T_Power, T_TT1, failure counts, simplified metric |
| `environment.json` | machine, Docker and ClickHouse versions, effective memory limit, other containers, settings, git commit, SHA-256 of the query files |

Before measured runs, `docker ps` must show only `infoh419-clickhouse`: the harness warns otherwise,
because ClickHouse's memory limit follows the free memory (protocol, section 1).

## Tests

```bash
python3 -m unittest part1-tpcds/scripts/test_harness.py -v
```

The ClickHouse tests are skipped when no server answers on `localhost:8123`.
