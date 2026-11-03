#!/usr/bin/env bash
# Relaunch the whole Part I benchmark (TPC-DS on ClickHouse) with one command, from a fresh clone:
#
#   ./run.sh            check at SF 1, campaigns at SF 12, 20, 30 and 50, then the charts
#                       (about 3 hours; README.md gives the memory and disk needed)
#   ./run.sh 1          quick run: check at SF 1, then one campaign at SF 1 (about 10 minutes)
#   ./run.sh 12 20      check at SF 1, then campaigns at the given scale factors
#
# The steps are those of README.md, "Part I". The check at SF 1 compares the results of the 99 queries
# with the reference answers and stops the run if one differs. Each campaign writes its results to
# part1-tpcds/results/sf<SF>/<run_id>/. Everything printed also goes to data/run-<time>.log.
# Environment variables:
#   KEEP=1        keep the raw files and the database of each scale factor (by default they are deleted
#                 after its campaign, to save disk space)
#   SKIP_CHECK=1  skip the check at SF 1
set -euo pipefail
cd "$(dirname "$0")"

[ $# -gt 0 ] || set -- 12 20 30 50
for N in "$@"; do
  case $N in ''|*[!0-9]*) echo "usage: ./run.sh [SF ...], with integer scale factors" >&2; exit 2 ;; esac
done

mkdir -p data                      # before ClickHouse starts, otherwise Docker creates data/ as root
LOG="data/run-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
START=$(date +%s)
COMPOSE="docker compose -f docker/docker-compose.yml"

step() { printf '\n== %s  %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf 'WARNING: %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*"; exit 1; }
sql() { $COMPOSE exec -T clickhouse clickhouse-client --password infoh419 --query "$1"; }

# compare.py prints one status per statement, then a last line such as "103 OK (of 103)"
check_results() {
  python3 part1-tpcds/scripts/compare.py "$1" "$2" > "$2/compare.txt"
  local last re='^([0-9]+) OK \(of ([0-9]+)\)$'
  last=$(tail -n 1 "$2/compare.txt")
  echo "$last"
  if ! [[ $last =~ $re ]] || [ "${BASH_REMATCH[1]}" != "${BASH_REMATCH[2]}" ]; then
    grep -v ' OK' "$2/compare.txt" | head -20 || true
    die "results differ from the reference answers (details in $2/compare.txt)"
  fi
}

step "Prerequisites"
command -v docker >/dev/null || die "docker not found (README.md, Requirements)"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 ('docker compose') not found"
docker info >/dev/null 2>&1 || die "Docker is not running: start Docker Desktop or the Docker service"
command -v python3 >/dev/null || die "python3 not found"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or later is needed"
[ -f tools/DSGen-software-code-4.0.0/tools/Makefile.suite ] \
  || die "the TPC-DS tools are missing in tools/DSGen-software-code-4.0.0 (tools/README.md)"
case $PWD in /mnt/[a-z]/*) warn "the repository is on a Windows drive: data generation is about 30 times slower" ;; esac
export UID; GID=$(id -g); export GID   # the TPC-DS tools container writes to data/ as this user

MAX=$(printf '%s\n' "$@" | sort -n | tail -n 1)
FREE=$(python3 -c 'import shutil; print(shutil.disk_usage(".").free // 10**9)')
NEED=$((MAX * 32 / 10 + 5))            # README.md, "Expected time and disk use": about 160 GB for SF 50
echo "scale factors: $*   free disk: $FREE GB   log: $LOG"
[ "$FREE" -ge "$NEED" ] || warn "about $NEED GB of free disk is advised for SF $MAX, only $FREE GB are free"

step "Start ClickHouse"
$COMPOSE up -d --wait
VERSION=$(sql "SELECT version()")
[ "$VERSION" = 26.8.24.9 ] || die "ClickHouse $VERSION is running, 26.8.24.9 is expected"
echo "ClickHouse $VERSION"
OTHERS=$(docker ps --format '{{.Names}}' | grep -vx infoh419-clickhouse || true)
[ -z "$OTHERS" ] || warn "other containers are running ($(echo $OTHERS)): they lower ClickHouse's memory limit, stop them for measured runs"

if [ "${SKIP_CHECK:-0}" != 1 ]; then
  step "Check at SF 1: the 99 queries against the reference answers"
  python3 part1-tpcds/scripts/gen_data.py --sf 1 --force
  python3 part1-tpcds/scripts/load.py --sf 1
  python3 part1-tpcds/scripts/gen_queries.py validation
  python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/validation \
          --out data/validation/sf1 --quiet
  check_results part1-tpcds/reference/sf1 data/validation/sf1
  step "Check at SF 1: the queries with the official qualification parameters"
  python3 part1-tpcds/scripts/gen_qualify.py
  python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/qualify \
          --out data/validation/sf1_qualify --quiet
  check_results part1-tpcds/reference/sf1_qualify data/validation/sf1_qualify
fi

for N in "$@"; do
  step "SF $N: generate the data and the query streams"
  python3 part1-tpcds/scripts/gen_data.py --sf "$N" --force
  python3 part1-tpcds/scripts/gen_queries.py streams --sf "$N"
  step "SF $N: campaign (load test, power test, throughput test, cold and warm power runs)"
  python3 part1-tpcds/scripts/harness.py campaign --sf "$N" --streams-dir "data/queries/sf$N" \
          --load-cmd "python3 part1-tpcds/scripts/load.py --sf $N" --quiet
  if [ "${KEEP:-0}" != 1 ]; then
    rm -f "data/tpcds/sf$N/"*.dat      # dsdgen is deterministic: gen_data.py can recreate them
    sql "DROP DATABASE IF EXISTS tpcds_sf$N"
  fi
done

step "Charts and tables of the report"
if ! .venv/bin/python -c 'import pandas, matplotlib' 2>/dev/null; then
  { python3 -m venv .venv && .venv/bin/pip install --quiet pandas matplotlib; } || true
fi
if .venv/bin/python -c 'import pandas, matplotlib' 2>/dev/null; then
  .venv/bin/python part1-tpcds/analysis/make_charts.py >/dev/null && echo "report/part1/figures/" \
    || warn "make_charts.py failed"
else
  warn "no charts: pandas and matplotlib could not be installed in .venv (on Debian/Ubuntu: sudo apt install python3-venv)"
fi

step "Summary"
python3 - "$@" <<'EOF'
import json
import sys
from pathlib import Path

print(f"{'SF':>4} {'run':16} {'T_Load':>9} {'T_Power':>9} {'T_TT1':>9} {'failures':>8} {'metric':>9}")
for sf in sys.argv[1:]:
    run = sorted(Path(f"part1-tpcds/results/sf{sf}").glob("*/summary.json"))[-1]
    s = json.loads(run.read_text())
    fails = sum(r["failures"] for test in ("power", "throughput", "power_cold", "power_warm") for r in s[test])
    print(f"{sf:>4} {run.parent.name:16} {s['load']['t_load_s']:8.1f}s {s['power'][0]['t_power_s']:8.1f}s "
          f"{s['throughput'][0]['t_tt1_s']:8.1f}s {fails:8d} {s['simplified_metric']:9,}")
EOF
ELAPSED=$(( $(date +%s) - START ))
printf '\nDone in %d h %02d min. Results: part1-tpcds/results/. Log: %s\n' $((ELAPSED / 3600)) $((ELAPSED % 3600 / 60)) "$LOG"
