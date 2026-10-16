"""Compare ClickHouse query results against the reference answers (DuckDB).

Usage:  python compare.py <reference_dir> <results_dir>
Each directory holds one CSV per query: q01.csv, q02.csv, q14_1.csv, ...
"""
import sys
from pathlib import Path

import pandas as pd


def norm(df):
    df = df.copy()
    df.columns = range(df.shape[1])  # ignore column names
    for c in df:
        num = pd.to_numeric(df[c], errors="coerce")
        if num.notna().sum() == df[c].notna().sum():  # numeric column -> round to 2 decimals
            df[c] = num.round(2).map(lambda x: "NULL" if pd.isna(x) else f"{x:.2f}")
        else:
            df[c] = df[c].map(lambda x: "NULL" if pd.isna(x) else str(x).strip())
    return df


def compare(ref, res):
    try:
        a, b = norm(pd.read_csv(ref)), norm(pd.read_csv(res))
    except pd.errors.EmptyDataError:
        return "CHECK (empty)"
    if a.shape != b.shape:
        return f"MISMATCH rows/cols {a.shape} vs {b.shape}"
    if a.equals(b):
        return "OK"
    sa = a.sort_values(list(a.columns)).reset_index(drop=True)
    sb = b.sort_values(list(b.columns)).reset_index(drop=True)
    return "OK (different order)" if sa.equals(sb) else "MISMATCH values"


if __name__ == "__main__":
    ref_dir, res_dir = map(Path, sys.argv[1:3])
    rows = []
    for ref in sorted(ref_dir.glob("q*.csv")):
        res = res_dir / ref.name
        rows.append((ref.stem, compare(ref, res) if res.exists() else "MISSING"))
        print(*rows[-1])
    pd.DataFrame(rows, columns=["query", "status"]).to_csv(res_dir / "status.csv", index=False)
