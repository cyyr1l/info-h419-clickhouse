"""Tests for compare.py (standard library only, everything in a temporary folder).

Run from the repo root:  python3 part1-tpcds/scripts/test_compare.py
"""
import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare  # noqa: E402

# name: (reference CSV, result CSV, expected status)
CASES = {
    "same values, other formatting": ("item,total\na,10.00\nb,20.50\nc,\n", "item,total\na,10\nb,20.5\nc,\n", "OK"),
    "other order": ("x,y\n1,a\n2,b\n", "x,y\n2,b\n1,a\n", "OK (different order)"),
    "float noise (Q47, Q63)": ("v\n5212.355\n", "v\n5212.3550000000005\n", "OK"),
    "template casts to decimal(15,4) (Q49)": ("r\n0.46371428\n", "r\n0.4637\n", "OK"),
    "truncation to 2 decimals": ("r\n1.1693\n", "r\n1.16\n", "MISMATCH values"),
    "another rounding mode (Q78)": ("r\n2.13\n", "r\n2.12\n", "MISMATCH values"),
    "nan is not NULL (Q17)": ('s\n""\n', "s\nnan\n", "MISMATCH values"),
    "one-column NULL as a blank line (Q23)": ('s\n""\n', "s\n\n", "OK"),
    "integers must be exact": ("n\n1000000\n", "n\n1000001\n", "MISMATCH values"),
    "missing row": ("x\n1\n2\n", "x\n1\n", "MISMATCH rows/cols (2, 1) vs (1, 1)"),
    "both empty": ("x,y\n", "x,y\n", "OK (both empty)"),
    "empty result file": ("x\n1\n", "", "CHECK (empty file)"),
}


class Compare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_cases(self):
        for name, (ref, res, expected) in CASES.items():
            with self.subTest(name):
                status, _ = compare.compare(self.write("ref.csv", ref), self.write("res.csv", res))
                self.assertEqual(status, expected)

    def test_mismatch_shows_the_first_difference(self):
        _, detail = compare.compare(self.write("ref.csv", "a,b\nx,1.17\n"), self.write("res.csv", "a,b\nx,1.16\n"))
        self.assertEqual(detail, "row 1, column 2: reference 1.17, result 1.16")

    def test_main_writes_status_csv_and_reports_missing_files(self):
        ref, res = self.dir / "ref", self.dir / "res"
        ref.mkdir()
        res.mkdir()
        for d in (ref, res):
            (d / "q01.csv").write_text("x\n1\n", encoding="utf-8")
        (ref / "q02.csv").write_text("x\n1\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            compare.main([str(ref), str(res)])
        with (res / "status.csv").open(newline="") as f:
            statuses = {r["query"]: r["status"] for r in csv.DictReader(f)}
        self.assertEqual(statuses, {"q01": "OK", "q02": "MISSING"})


if __name__ == "__main__":
    unittest.main()
