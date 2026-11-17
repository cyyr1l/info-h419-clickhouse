#!/usr/bin/env python3
"""Generate the TPC-DI data of one scale factor with DIGen 1.1.0 (Java 8, in Docker).

Usage (from the repository root):
  python3 part2-tpcdi/scripts/gen_data.py --sf 10        # -> data/tpcdi/sf10/

Output: data/tpcdi/sf<SF>/Batch1, Batch2, Batch3, the *_audit.csv files, digen_report.txt
and manifest.json (generation time and sizes). This folder is the Staging Area: never
modify it. An existing sf<SF> folder is never overwritten (delete it first).

Requires the DIGen zip from tpc.org in tools/ (*TPC-DI-Tool.zip). The first run builds the
Docker image infoh419/tpcdi-digen:1.1.0.

DIGen pitfalls handled here:
  - it asks to accept the licence: ENTER then YES are sent on stdin, and stdin stays open
    until digen_report.txt exists (DIGen aborts if stdin closes earlier);
  - its exit code is 0 even when it fails: success is checked on the output instead
    (digen_report.txt with the record totals, 3 batches, the main source files).

Standard library only.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(REPO / "docker" / "docker-compose.yml"), "--profile", "tools"]
MB_PER_SF = 100            # SF 10 is about 960 MiB of raw files
EXPECTED = {               # files that must exist in every generated data set
    "Batch1": ["BatchDate.txt", "CustomerMgmt.xml", "Prospect.csv", "HR.csv", "Date.txt", "Time.txt",
               "StatusType.txt", "TradeType.txt", "Industry.txt", "TaxRate.txt", "Trade.txt",
               "TradeHistory.txt", "CashTransaction.txt", "HoldingHistory.txt", "DailyMarket.txt",
               "WatchHistory.txt"],
    "Batch2": ["BatchDate.txt", "Customer.txt", "Account.txt", "Prospect.csv", "Trade.txt",
               "CashTransaction.txt", "HoldingHistory.txt", "DailyMarket.txt", "WatchHistory.txt"],
    "Batch3": ["BatchDate.txt", "Customer.txt", "Account.txt", "Prospect.csv", "Trade.txt",
               "CashTransaction.txt", "HoldingHistory.txt", "DailyMarket.txt", "WatchHistory.txt"],
}


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def run_digen(sf, out_rel, report):
    """Run DIGen in the container, answer the licence prompt, keep stdin open until done."""
    env = dict(os.environ)
    if hasattr(os, "getuid"):
        env.setdefault("UID", str(os.getuid()))
        env.setdefault("GID", str(os.getgid()))
    command = COMPOSE + ["run", "--rm", "-T", "tpcdi-digen",
                         "java", "-jar", "DIGen.jar", "-sf", str(sf), "-o", f"/data/{out_rel}"]
    print("$", " ".join(command[4:]))
    process = subprocess.Popen(command, stdin=subprocess.PIPE, env=env)
    try:
        process.stdin.write(b"\nYES\n")
        process.stdin.flush()
        while process.poll() is None:
            if report.is_file() and not process.stdin.closed:
                process.stdin.close()
            time.sleep(1)
    except KeyboardInterrupt:
        process.terminate()
        raise
    finally:
        if not process.stdin.closed:
            process.stdin.close()
    return process.wait()


def check_output(out_dir, report):
    """DIGen's exit code means nothing: check what it wrote."""
    if not report.is_file():
        fail(f"{report} was not written: DIGen failed (see its output above).")
    text = report.read_text(errors="replace")
    totals = {int(n): int(v) for n, v in re.findall(r"TotalRecords for Batch(\d): (\d+)", text)}
    match = re.search(r"TotalRecords all Batches: (\d+)", text)
    if sorted(totals) != [1, 2, 3] or not match:
        fail(f"{report} has no record totals for the 3 batches: DIGen did not finish.")
    missing = [f"{batch}/{name}" for batch, names in EXPECTED.items()
               for name in names if not (out_dir / batch / name).is_file()]
    finwire = list((out_dir / "Batch1").glob("FINWIRE????Q?"))
    if not finwire:
        missing.append("Batch1/FINWIRE*")
    if missing:
        fail("missing files: " + ", ".join(missing))
    empty = [str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file() and p.stat().st_size == 0
             and p.name != "BatchDate.txt"]
    return totals, int(match.group(1)), len(finwire), empty


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sf", type=int, required=True, help="scale factor, at least 3 (DIGen minimum)")
    args = parser.parse_args(argv)
    if args.sf < 3:
        fail("DIGen needs a scale factor of at least 3.")

    out_rel = f"tpcdi/sf{args.sf}"
    out_dir = REPO / "data" / out_rel
    report = out_dir / "digen_report.txt"
    if out_dir.exists():
        fail(f"{out_dir} already exists. The data set is deterministic: delete the folder to regenerate it.")
    if not list((REPO / "tools").glob("*TPC-DI-Tool.zip")):
        fail("no *TPC-DI-Tool.zip in tools/: download the TPC-DI tools from tpc.org "
             "(see the README) and put the zip in tools/.")
    (REPO / "data" / "tpcdi").mkdir(parents=True, exist_ok=True)
    need = int(1.2 * MB_PER_SF * args.sf * 2**20)
    free = shutil.disk_usage(REPO / "data").free
    if free < need:
        fail(f"not enough disk: {free / 2**30:.1f} GiB free, about {need / 2**30:.1f} GiB needed.")

    start = time.perf_counter()
    code = run_digen(args.sf, out_rel, report)
    seconds = time.perf_counter() - start
    print(f"DIGen exited with code {code} after {seconds:.0f} s (the code is not trusted, checking the output)")

    totals, total, finwire, empty = check_output(out_dir, report)
    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    manifest = {
        "sf": args.sf,
        "generator": "DIGen 1.1.0",
        "generation_seconds": round(seconds, 1),
        "records_per_batch": totals,
        "records_total": total,
        "finwire_files": finwire,
        "bytes": size,
        "empty_files": empty,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for batch, n in totals.items():
        print(f"  Batch{batch}: {n:,} records")
    if empty:
        print("  note: empty files:", ", ".join(empty))
    print(f"OK  SF {args.sf}: {total:,} records, {size / 2**30:.2f} GiB, {seconds:.0f} s -> {out_dir}")


if __name__ == "__main__":
    sys.exit(main())
