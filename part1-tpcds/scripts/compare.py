"""Compare ClickHouse query results against the reference answers (DuckDB). Standard library only.

Usage:  python3 compare.py <reference_dir> <results_dir>
Each directory holds one CSV with a header row per query: q01.csv, q02.csv, q14_1.csv, ...
Prints one status per reference file and writes <results_dir>/status.csv.

Rules (see README_validation.md):
- Column names are ignored. An empty field is NULL; nan and inf are values of their own.
- Integers must match exactly. Other numbers may differ by ABS_TOL or REL_TOL: enough for float
  noise and for the templates' own decimal(15,4) casts, strict enough to catch truncation to
  2 decimals or another rounding mode.
- Rows may come in another order ("OK (different order)").
"""
import csv
import math
import sys
from pathlib import Path

ABS_TOL, REL_TOL = 1e-4, 1e-9
SPECIAL = {"nan", "-nan", "inf", "-inf", "+inf", "infinity", "-infinity"}
KIND_ORDER = {"null": 0, "special": 1, "num": 2, "str": 3}


def cell(text):
    """Parse one field: ("null", ""), ("special", "nan"), ("num", 1.5) or ("str", "abc")."""
    t = text.strip()
    if t == "":
        return ("null", "")
    if t.lower() in SPECIAL:
        return ("special", t.lower().lstrip("+"))
    try:
        return ("num", float(t))
    except ValueError:
        return ("str", t)


def read(path):
    """Header and parsed rows of a result CSV; (None, []) for an empty file."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return None, []
    header, body = rows[0], rows[1:]
    if len(header) == 1:   # in a one-column result, a NULL can be written as a blank line
        body = [r if r else [""] for r in body]
    return header, [[cell(v) for v in r] for r in body]


def same(a, b):
    if a[0] != b[0]:
        return False
    if a[0] != "num":
        return a[1] == b[1]
    x, y = a[1], b[1]
    if x.is_integer() and y.is_integer():
        return x == y
    return math.isclose(x, y, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def same_row(r, s):
    return len(r) == len(s) and all(same(a, b) for a, b in zip(r, s))


def row_key(row):
    return [(KIND_ORDER[k], round(v, 4) if k == "num" else 0.0, "" if k == "num" else v) for k, v in row]


def same_multiset(a, b):
    """Every row of a matches a distinct row of b (rows are sorted, so matches are near the front)."""
    remaining = list(b)
    for row in a:
        for i, cand in enumerate(remaining):
            if same_row(row, cand):
                del remaining[i]
                break
        else:
            return False
    return True


def show(c):
    kind, v = c
    return "NULL" if kind == "null" else f"{v:.10g}" if kind == "num" else str(v)


def first_difference(a, b):
    for i, (r, s) in enumerate(zip(a, b), 1):
        for j, (x, y) in enumerate(zip(r, s), 1):
            if not same(x, y):
                return f"row {i}, column {j}: reference {show(x)}, result {show(y)}"
        if len(r) != len(s):
            return f"row {i}: {len(r)} vs {len(s)} fields"
    return ""


def compare(ref_path, res_path):
    """Return (status, detail) for one query."""
    ref_header, ref = read(ref_path)
    res_header, res = read(res_path)
    if res_header is None:
        return "CHECK (empty file)", "no header row"
    if len(ref) != len(res) or len(ref_header) != len(res_header):
        return (f"MISMATCH rows/cols ({len(ref)}, {len(ref_header)}) vs "
                f"({len(res)}, {len(res_header)})"), ""
    if not ref:
        return "OK (both empty)", "weak check: validate with the official parameters"
    if all(same_row(r, s) for r, s in zip(ref, res)):
        return "OK", ""
    sorted_ref, sorted_res = sorted(ref, key=row_key), sorted(res, key=row_key)
    if all(same_row(r, s) for r, s in zip(sorted_ref, sorted_res)) or same_multiset(sorted_ref, sorted_res):
        return "OK (different order)", ""
    return "MISMATCH values", first_difference(ref, res)


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        sys.exit("usage: python3 compare.py <reference_dir> <results_dir>")
    ref_dir, res_dir = map(Path, args)
    for d in (ref_dir, res_dir):
        if not d.is_dir():
            sys.exit(f"{d} is not a folder")
    rows = []
    for ref in sorted(ref_dir.glob("q*.csv")):
        res = res_dir / ref.name
        status, detail = compare(ref, res) if res.exists() else ("MISSING", "")
        rows.append((ref.stem, status, detail))
        print(f"{ref.stem:7s} {status}" + (f"  [{detail}]" if detail and not status.startswith("OK") else ""))
    with (res_dir / "status.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["query", "status", "detail"])
        w.writerows(rows)
    counts = {}
    for _, status, _ in rows:
        key = status.split(" (")[0] if not status.startswith("OK") else "OK"
        counts[key] = counts.get(key, 0) + 1
    print("\n" + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + f" (of {len(rows)})")


if __name__ == "__main__":
    main()
