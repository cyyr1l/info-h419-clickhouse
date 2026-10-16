#!/usr/bin/env bash
# Generate the 99 TPC-DS queries, one file per template (q01.sql ... q99.sql).
# Run from tpcds-kit/tools after building dsqgen.
# Usage: ./gen_queries.sh <output_dir> [scale]
# Note: in kit 4.0.0, -QUALIFY Y only orders the queries; parameters are still
# random (deterministic with the default seed), so they differ from answer_sets/.
set -euo pipefail
OUT=${1:?output dir}; SCALE=${2:-1}
mkdir -p "$OUT"
grep -q "_END" ../query_templates/netezza.tpl || echo 'define _END = "";' >> ../query_templates/netezza.tpl
for i in $(seq 1 99); do
  tmp=$(mktemp -d)
  ./dsqgen -DIRECTORY ../query_templates -TEMPLATE "query$i.tpl" -DIALECT netezza \
           -QUALIFY Y -SCALE "$SCALE" -OUTPUT_DIR "$tmp" >/dev/null 2>&1
  cp "$tmp/query_0.sql" "$OUT/q$(printf %02d "$i").sql"; rm -rf "$tmp"
done
echo "Generated $(ls "$OUT" | wc -l) queries in $OUT"
