#!/usr/bin/env bash
# Tests for the DImessages/Audit DDL and the Appendix B/C queries, on stub tables with toy data.
# Usage: part2-tpcdi/tests/audit/run_tests.sh [path/to/clickhouse-client-command]
#   default client: "clickhouse client"; uses a throwaway database "role4_test".
set -euo pipefail
cd "$(dirname "$0")/../.."
CH=${1:-"clickhouse client"}
DB=role4_test
q()   { $CH -d "$DB" -q "$1" </dev/null; }
run() { $CH -d "$DB" --multiquery < "$1"; }
fail=0
check() {  # check <description> <expected> <sql>
  local got; got=$(q "$3")
  if [[ "$got" == "$2" ]]; then echo "  ok   $1"; else echo "  FAIL $1: expected [$2], got [$got]"; fail=1; fi
}

$CH -q "DROP DATABASE IF EXISTS $DB" </dev/null
$CH -q "CREATE DATABASE $DB" </dev/null
run ddl/dimessages_audit.sql
run tests/audit/stub_dw.sql

echo "Batch 0 (empty DW)"
run scripts/audit/validation.sql
check "24 validation messages"        24 "SELECT count() FROM DImessages WHERE BatchID = 0 AND MessageType = 'Validation'"
check "all counts are 0"              0  "SELECT countIf(MessageData != '0') FROM DImessages WHERE BatchID = 0 AND MessageType = 'Validation'"
check "one PCR with NULL data"        1  "SELECT count() FROM DImessages WHERE BatchID = 0 AND MessageType = 'PCR' AND MessageData IS NULL"

echo "Batch 1 (toy data)"
q "INSERT INTO DImessages SELECT now64(3), 1, 'Orchestrator', 'Batch started', 'Status', NULL"
run tests/audit/toy_batch1.sql
run scripts/audit/visibility_1.sql
run scripts/audit/visibility_2.sql
run scripts/audit/validation.sql
v() { q "SELECT MessageData FROM DImessages WHERE BatchID = 1 AND MessageType = 'Validation' AND MessageSource = '$1' AND MessageText = '$2'"; }
check "24 validation messages"           24 "SELECT count() FROM DImessages WHERE BatchID = 1 AND MessageType = 'Validation'"
check "batch 1 PCR"                      1  "SELECT count() FROM DImessages WHERE BatchID = 1 AND MessageType = 'PCR'"
check "validation shares one timestamp"  1  "SELECT uniqExact(MessageDateAndTime) FROM DImessages WHERE BatchID = 1 AND MessageType = 'Validation'"
check "visibility_1: 22 messages, 1 ts"  "22	1" "SELECT count(), uniqExact(MessageDateAndTime) FROM DImessages WHERE MessageType = 'Visibility_1'"
check "visibility_2: 18 messages, 1 ts"  "18	1" "SELECT count(), uniqExact(MessageDateAndTime) FROM DImessages WHERE MessageType = 'Visibility_2'"
check "timestamp has milliseconds"       3  "SELECT toTypeName(MessageDateAndTime) = 'DateTime64(3)' ? 3 : 0 FROM DImessages LIMIT 1"
for spec in "DimAccount|Row count|3" "DimBroker|Row count|2" "DimCustomer|Row count|3" \
            "DimTrade|Row count|2" "FactCashBalances|Row count joined|1" "FactHoldings|Row count joined|1" \
            "FactMarketHistory|Row count joined|2" "FactWatches|Row count joined|2" \
            "DimCustomer|Inactive customers|1" "FactWatches|Inactive watches|1"; do
  IFS='|' read -r src txt exp <<< "$spec"
  got=$(v "$src" "$txt")
  if [[ "$got" == "$exp" ]]; then echo "  ok   $src / $txt = $exp"; else echo "  FAIL $src / $txt: expected $exp, got $got"; fail=1; fi
done

$CH -q "DROP DATABASE $DB" </dev/null
if [[ $fail == 0 ]]; then echo "All tests passed"; else echo "Some tests FAILED"; exit 1; fi
