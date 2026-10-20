#!/usr/bin/env python3
"""Generate the TPC-DS data for one scale factor and check it (role 1).

Runs dsdgen in the tpcds-kit Docker image, in parallel, and writes the flat files to
data/tpcds/sf<SF>/ (ignored by git). Then checks the 24 tables, because dsdgen exits
with code 0 even when it fails:

  1. no "ERROR" in the dsdgen output;
  2. every table has its files, every chunk of a split table is there, and every file
     ends with a newline (a truncated file, e.g. disk full, does not);
  3. row counts:
     - 18 tables have an exact row count, computed by the kit's own scaling code
       (docker/tpcds-kit/rowcounts.c): the count must match exactly;
     - store_sales, catalog_sales, web_sales: the kit fixes the number of orders, and each
       order gets a uniform random number of line items (8-16, 4-14 and 8-16). The average
       number of rows per order must be within 1% of 12, 9 and 12;
     - the 3 returns tables: each sale is returned with probability 10% (constants.h). The
       ratio returns / sales must be within 2% of 10%.

The results go to data/tpcds/sf<SF>/manifest.json (rows per table, files, checks, timing),
which the loader uses to check the row counts in ClickHouse.

  python3 part1-tpcds/scripts/gen_data.py --sf 10              # generate + check
  python3 part1-tpcds/scripts/gen_data.py --sf 10 --jobs 8     # number of parallel dsdgen processes
  python3 part1-tpcds/scripts/gen_data.py --sf 10 --force      # delete existing files first
  python3 part1-tpcds/scripts/gen_data.py --sf 10 --check-only # only check existing files

dsdgen is deterministic: the same SF gives the same rows on every machine and for any
--jobs value. Only tables with at least 1,000,000 rows (orders for the sales tables) are
split into chunks (<table>_<i>_<jobs>.dat); the others are written by the first process
only and renamed to <table>.dat.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker" / "docker-compose.yml"
KIT_VERSION = "4.0.0"

# sales table -> (min, max) line items per order (w_*_sales.c)
LINE_ITEMS = {"store_sales": (8, 16), "catalog_sales": (4, 14), "web_sales": (8, 16)}
RETURNS = {"store_returns": "store_sales", "catalog_returns": "catalog_sales",
           "web_returns": "web_sales"}
RETURN_RATE = 0.10                  # SR/CR/WR_RETURN_PCT = 10 in constants.h
ITEMS_TOLERANCE = 0.01              # relative, on the mean line items per order
RETURNS_TOLERANCE = 0.02            # relative, on the returns / sales ratio
NOT_A_TABLE = {"dbgen_version"}     # written by dsdgen, not one of the 24 TPC-DS tables
BYTES_PER_SF = 1.3e9                # raw size: SF 1 is about 1.2 GB


def fmt_sf(sf):
    return str(int(sf)) if float(sf).is_integer() else str(sf)


def run_in_kit(script, capture=True):
    """Run a shell script in the tpcds-kit container (repo data/ is mounted as /data)."""
    cmd = ["docker", "compose", "-f", str(COMPOSE), "run", "--rm", "tpcds-kit",
           "sh", "-c", script]
    return subprocess.run(cmd, capture_output=capture, text=True)


def expected_rowcounts(sf):
    """{table: (rows, kind)} from the kit's scaling code (kind: exact, orders, child)."""
    r = run_in_kit(f"rowcounts -SCALE {fmt_sf(sf)} -QUIET Y")
    if r.returncode != 0:
        sys.exit("rowcounts failed (rebuild the image: cd docker && docker compose build tpcds-kit)\n"
                 f"{r.stdout}\n{r.stderr}")
    out = {}
    for line in r.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            out[parts[0]] = (int(parts[1]), parts[2])
    tables = {t: v for t, v in out.items() if t not in NOT_A_TABLE}
    if len(tables) != 24:
        sys.exit(f"rowcounts returned {len(tables)} tables instead of 24:\n{r.stdout}")
    return tables


def generate(sf, jobs, out_dir):
    """Run <jobs> dsdgen processes in one container; returns the elapsed time in seconds."""
    target = f"/data/tpcds/sf{fmt_sf(sf)}"
    par = f"-PARALLEL {jobs} -CHILD $c " if jobs > 1 else ""
    script = f"""
mkdir -p {target}/_logs
pids=""
for c in $(seq 1 {jobs}); do
  dsdgen -SCALE {fmt_sf(sf)} {par}-DIR {target} -TERMINATE N -FORCE Y \\
         > {target}/_logs/dsdgen_$c.log 2>&1 &
  pids="$pids $!"
done
rc=0
for p in $pids; do wait $p || rc=1; done
exit $rc
"""
    print(f"== generating SF {fmt_sf(sf)} with {jobs} dsdgen process(es) into {out_dir}")
    t0 = time.perf_counter()
    r = run_in_kit(script, capture=False)
    elapsed = time.perf_counter() - t0
    if r.returncode != 0:
        print(f"!! a dsdgen process exited with code != 0 (see {out_dir / '_logs'})")
    print(f"== generation took {elapsed:.0f} s")
    return elapsed, r.returncode


def rename_single_chunks(out_dir):
    """<table>_1_<n>.dat with no other chunk -> <table>.dat (small tables are not split)."""
    chunks = {}
    for f in out_dir.glob("*.dat"):
        m = re.fullmatch(r"(.+)_(\d+)_(\d+)", f.stem)
        if m:
            chunks.setdefault(m.group(1), []).append((int(m.group(2)), f))
    for table, files in chunks.items():
        if len(files) == 1 and files[0][0] == 1:
            files[0][1].rename(out_dir / f"{table}.dat")


def table_files(out_dir, table):
    """Files of one table and the problems found with them."""
    plain = out_dir / f"{table}.dat"
    chunks = sorted(out_dir.glob(f"{table}_*_*.dat"),
                    key=lambda p: int(p.stem.rsplit("_", 2)[1]))
    chunks = [c for c in chunks if re.fullmatch(rf"{re.escape(table)}_\d+_\d+", c.stem)]
    problems = []
    if plain.exists() and chunks:
        problems.append("both a plain file and chunk files")
    files = ([plain] if plain.exists() else []) + chunks
    if not files:
        return [], ["no file"]
    if chunks:
        n = int(chunks[0].stem.rsplit("_", 1)[1])
        have = {int(c.stem.rsplit("_", 2)[1]) for c in chunks}
        missing = sorted(set(range(1, n + 1)) - have)
        if missing:
            problems.append(f"missing chunks {missing} of {n}")
    for f in files:
        size = f.stat().st_size
        if size == 0:
            problems.append(f"{f.name} is empty")
            continue
        with open(f, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                problems.append(f"{f.name} does not end with a newline (truncated?)")
    return files, problems


def count_lines(path, bufsize=64 * 1024 * 1024):
    n = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(bufsize):
            n += chunk.count(b"\n")
    return n


def scan_logs(out_dir):
    errors = []
    for log in sorted((out_dir / "_logs").glob("*.log")):
        for line in log.read_text(errors="replace").splitlines():
            if "ERROR" in line or "Failed" in line:
                errors.append(f"{log.name}: {line.strip()}")
    return errors


def check(sf, out_dir, expected):
    """Check the files of the 24 tables; returns (tables dict, list of failures)."""
    failures = [f"dsdgen output: {e}" for e in scan_logs(out_dir)]
    tables = {}
    for table in sorted(expected):
        files, problems = table_files(out_dir, table)
        rows = sum(count_lines(f) for f in files)
        tables[table] = {"rows": rows, "files": [f.name for f in files],
                         "bytes": sum(f.stat().st_size for f in files),
                         "expected": expected[table][0], "kind": expected[table][1],
                         "problems": problems}
        print(f"   {table:24s} {rows:>13,} rows  {len(files):>3} file(s)")

    for table, info in tables.items():
        kind, exp, rows = info["kind"], info["expected"], info["rows"]
        if kind == "exact" and rows != exp:
            info["problems"].append(f"{rows:,} rows, expected exactly {exp:,}")
        elif kind == "orders":
            lo, hi = LINE_ITEMS[table]
            mean, target = rows / exp, (lo + hi) / 2
            info["items_per_order"] = round(mean, 4)
            if abs(mean - target) / target > ITEMS_TOLERANCE:
                info["problems"].append(f"{mean:.3f} rows per order, expected {target} "
                                        f"± {ITEMS_TOLERANCE:.0%} ({exp:,} orders)")
        elif kind == "child":
            sales = tables[RETURNS[table]]["rows"]
            ratio = rows / sales if sales else 0
            info["return_ratio"] = round(ratio, 5)
            if abs(ratio - RETURN_RATE) / RETURN_RATE > RETURNS_TOLERANCE:
                info["problems"].append(f"returns / sales = {ratio:.4f}, expected "
                                        f"{RETURN_RATE} ± {RETURNS_TOLERANCE:.0%}")
        failures += [f"{table}: {p}" for p in info["problems"]]
    return tables, failures


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sf", type=int, required=True, help="scale factor (integer, e.g. 10)")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                   help="parallel dsdgen processes (default: number of CPU threads)")
    p.add_argument("--out", type=Path, help="default: data/tpcds/sf<SF> (must stay under data/)")
    p.add_argument("--force", action="store_true", help="delete existing files of this SF first")
    p.add_argument("--check-only", action="store_true", help="only check existing files")
    args = p.parse_args(argv)

    out_dir = (args.out or REPO / "data" / "tpcds" / f"sf{fmt_sf(args.sf)}").resolve()
    if out_dir != (REPO / "data" / "tpcds" / f"sf{fmt_sf(args.sf)}").resolve():
        sys.exit("--out must be data/tpcds/sf<SF>: only data/ is mounted in the container")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("== building the tpcds-kit image (cached after the first time)")
    if subprocess.run(["docker", "compose", "-f", str(COMPOSE), "build", "-q", "tpcds-kit"]).returncode:
        sys.exit("docker compose build tpcds-kit failed")
    expected = expected_rowcounts(args.sf)

    gen_s, rc = None, 0
    if not args.check_only:
        existing = list(out_dir.glob("*.dat"))
        if existing and not args.force:
            sys.exit(f"{out_dir} already has {len(existing)} .dat files: use --force to regenerate "
                     "or --check-only to check them")
        for f in existing:
            f.unlink()
        shutil.rmtree(out_dir / "_logs", ignore_errors=True)
        (out_dir / "manifest.json").unlink(missing_ok=True)

        need = args.sf * BYTES_PER_SF
        free = shutil.disk_usage(out_dir).free
        if free < need * 1.1:
            sys.exit(f"not enough disk: about {need / 1e9:.0f} GB needed, {free / 1e9:.0f} GB free")
        gen_s, rc = generate(args.sf, max(1, args.jobs), out_dir)
        rename_single_chunks(out_dir)

    print("== checking the 24 tables")
    tables, failures = check(args.sf, out_dir, expected)
    if rc:
        failures.insert(0, "a dsdgen process exited with a non-zero code")

    manifest = {
        "sf": args.sf, "kit_version": KIT_VERSION,
        "jobs": None if args.check_only else args.jobs,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generation_s": None if gen_s is None else round(gen_s, 1),
        "total_rows": sum(t["rows"] for t in tables.values()),
        "total_bytes": sum(t["bytes"] for t in tables.values()),
        "status": "ok" if not failures else "failed",
        "failures": failures,
        "tables": tables,
    }
    if args.check_only and (out_dir / "manifest.json").exists():
        old = json.loads((out_dir / "manifest.json").read_text())
        manifest["jobs"], manifest["generation_s"] = old.get("jobs"), old.get("generation_s")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"== {manifest['total_rows']:,} rows, {manifest['total_bytes'] / 1e9:.2f} GB "
          f"-> {out_dir / 'manifest.json'}")
    if failures:
        print(f"!! {len(failures)} problem(s):")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    print("== OK: all 24 tables passed the checks")


if __name__ == "__main__":
    main()
