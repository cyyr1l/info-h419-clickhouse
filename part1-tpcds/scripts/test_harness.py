"""Tests for harness.py (standard library only).

Run from the repo root:  python3 -m unittest part1-tpcds/scripts/test_harness.py -v
The ClickHouse tests are skipped when no server answers on localhost:8123.
"""
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

STREAM = """\
-- start query 1 in stream 0 using template query96.tpl
select count(*)
from store_sales
limit 100;

-- end query 1 in stream 0 using template query96.tpl
-- start query 2 in stream 0 using template query14.tpl
with x as (select 1) select * from x;
with y as (select 2) select * from y;
-- end query 2 in stream 0 using template query14.tpl
"""


class ParseStream(unittest.TestCase):
    def test_markers_give_position_template_and_statements(self):
        queries = harness.parse_stream(STREAM)
        self.assertEqual([(q.position, q.template, len(q.statements)) for q in queries],
                         [(1, 96, 1), (2, 14, 2)])
        self.assertEqual(queries[0].statements[0], "select count(*)\nfrom store_sales\nlimit 100")

    def test_stream_number_is_read_from_markers(self):
        self.assertEqual(harness.stream_number(STREAM), 0)
        self.assertIsNone(harness.stream_number("select 1;"))

    def test_file_without_markers_is_one_query_named_by_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "q07.sql")
            f.write_text("select 1;\n")
            (q,) = harness.load_queries([f])
            self.assertEqual((q.position, q.template, q.statements), (7, 7, ["select 1"]))

    def test_directory_is_read_in_template_order(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (10, 2, 1):
                Path(d, f"q{n:02d}.sql").write_text(f"select {n};")
            self.assertEqual([q.template for q in harness.load_queries([Path(d)])], [1, 2, 10])

    def test_comment_only_chunks_are_not_statements(self):
        self.assertEqual(harness.split_statements("select 1;\n-- trailing comment\n;  \n"), ["select 1"])


class Helpers(unittest.TestCase):
    def test_parse_only(self):
        self.assertEqual(harness.parse_only("26-28,30"), {26, 27, 28, 30})
        self.assertIsNone(harness.parse_only(None))

    def test_result_file_names_follow_the_reference_answers(self):
        self.assertEqual(harness.result_name(5, 1, 1), "q05")
        self.assertEqual(harness.result_name(14, 2, 2), "q14_2")

    def test_error_classification(self):
        self.assertEqual(harness.classify(159), "timeout")
        self.assertEqual(harness.classify(241), "memory")
        self.assertEqual(harness.classify(62), "error")

    def test_settings_sections_are_merged_and_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "s.json")
            f.write_text(json.dumps({"about": "x", "sql_compatibility": {"join_use_nulls": 1},
                                     "benchmark": {"use_query_cache": 0}}))
            self.assertEqual(harness.load_settings(f), {"join_use_nulls": 1, "use_query_cache": 0})
            f.write_text(json.dumps({"sql_compatibility": {"a": 1}, "benchmark": {"a": 2}}))
            with self.assertRaises(ValueError):
                harness.load_settings(f)

    def test_official_metric_reproduces_a_published_result(self):
        # Tencent TDSQL, SF 10000 (TPC full disclosure report): 72,603,042 QphDS@10000GB
        sq = 4
        t = harness.qphds(sf=10000, sq=sq, t_power_s=0.4144 / sq * 3600, t_tt_s=0.4268 * 3600,
                          t_dm_s=0.0139 * 3600, t_load_s=0.0036 / (0.01 * sq) * 3600)
        self.assertEqual(t, 72603042)

    def test_simplified_metric(self):
        # SF 1, Sq 4, T_Power 1 h, T_TT1 4 h, T_Load 1 h: Q=396, T_PT=4, T_TT=4, T_LD=0.04
        self.assertEqual(harness.simplified_metric(1, 4, 3600, 4 * 3600, 3600), int(396 / (4 * 4 * 0.04) ** (1 / 3)))


def clickhouse_up():
    try:
        socket.create_connection(("localhost", 8123), timeout=1).close()
        return True
    except OSError:
        return False


@unittest.skipUnless(clickhouse_up(), "ClickHouse is not running on localhost:8123")
class WithClickHouse(unittest.TestCase):
    def setUp(self):
        self.ch = harness.ClickHouse("localhost", 8123, "default", "infoh419", "default", {}, timeout=30)

    def tearDown(self):
        self.ch.close()

    def test_ok_query_returns_rows(self):
        r = self.ch.execute("SELECT number FROM numbers(3)", query_id=harness.new_query_id("test"))
        self.assertEqual((r.status, r.client_rows), ("ok", 3))

    def test_syntax_error_is_reported_with_its_code(self):
        r = self.ch.execute("SELEC 1", query_id=harness.new_query_id("test"))
        self.assertEqual(r.status, "error")
        self.assertTrue(r.error.startswith("62:"), r.error)

    def test_timeout_is_classified(self):
        r = self.ch.execute("SELECT count() FROM numbers(3000) WHERE sleepEachRow(0.001) = 0",
                            query_id=harness.new_query_id("test"),
                            settings={"max_execution_time": 1, "max_block_size": 100})
        self.assertEqual(r.status, "timeout")

    def test_settings_check_before_a_load_does_not_need_the_database(self):
        args = harness.build_parser().parse_args(
            ["load", "--sf", "1", "--database", "db_created_by_the_loader", "--", "true"])
        harness.preflight_settings(args)   # must not exit: the loader creates the database

    def test_server_stats_come_from_the_query_log(self):
        qid = harness.new_query_id("test")
        self.ch.execute("SELECT sum(number) FROM numbers(1000)", query_id=qid)
        stats = self.ch.server_stats([qid])
        self.assertEqual(stats[qid]["read_rows"], 1000)
        self.assertEqual(stats[qid]["result_rows"], 1)


if __name__ == "__main__":
    unittest.main()
