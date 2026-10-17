-- ClickHouse dialect for dsqgen (TPC-DS kit 4.0.0), used with -DIALECT clickhouse.
-- Same LIMIT syntax as netezza.tpl, plus a marker line before and after each query
-- (kit 4.0.0 no longer defines them). The harness uses the markers to split a stream.
-- See docs/benchmark-protocol.md, section 7.
define __LIMITA = "";
define __LIMITB = "";
define __LIMITC = "limit %d";
define _BEGIN = "-- start query " + [_QUERY] + " in stream " + [_STREAM] + " using template " + [_TEMPLATE];
define _END = "-- end query " + [_QUERY] + " in stream " + [_STREAM] + " using template " + [_TEMPLATE];
