#!/usr/bin/env python3
"""Generate the TPC-DS queries with dsqgen (docs/benchmark-protocol.md, section 7).

Runs dsqgen in the tpcds-kit Docker image on the kit's templates
(tools/DSGen-software-code-4.0.0/query_templates). For ClickHouse, the templates are first
overlaid with part1-tpcds/queries/templates/ (the clickhouse dialect and our fixed templates),
and '+ N days' is then rewritten to '+ INTERVAL N DAY'.

  python3 part1-tpcds/scripts/gen_queries.py validation        # data/queries/validation/qNN.sql
  python3 part1-tpcds/scripts/gen_queries.py streams --sf 10   # data/queries/sf10/query_0..4.sql
  python3 part1-tpcds/scripts/gen_queries.py original          # data/queries/original/qNN.sql

validation  one file per template, SF 1, -QUALIFY Y and the default seed: the parameters of
            queries/original/ and of the reference answers.
streams     stream 0 (power test) and streams 1-4 (throughput test) for one SF, seed 20261101.
original    queries/original/ exactly (netezza dialect, no overlay, no rewrite).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KIT = REPO / "tools" / "DSGen-software-code-4.0.0" / "query_templates"
OVERLAY = REPO / "part1-tpcds" / "queries" / "templates"
COMPOSE = REPO / "docker" / "docker-compose.yml"
SEED = 20261101
START = re.compile(r"^-- start query \d+ in stream \d+ using template query\d+\.tpl", re.M)
DAYS = re.compile(r"(?<![\w'])(\d+) days\b")   # same rewrite as build_reference.py

PER_TEMPLATE = """
for i in $(seq 1 99); do
  rm -rf /qgen/tmp && mkdir /qgen/tmp
  dsqgen -DIRECTORY /qgen/templates -TEMPLATE query$i.tpl -DIALECT {dialect} -QUALIFY Y -SCALE 1 \\
         -OUTPUT_DIR /qgen/tmp > /dev/null 2>&1 || true
  [ -s /qgen/tmp/query_0.sql ] || {{ echo "dsqgen produced nothing for query$i.tpl"; exit 1; }}
  cp /qgen/tmp/query_0.sql /qgen/out/q$(printf %02d $i).sql
done
rm -rf /qgen/tmp
"""


def rewrite(sql):
    return DAYS.sub(r"INTERVAL \1 DAY", sql)


def run_in_kit(work, script):
    """Run a shell script in the tpcds-kit container, with <work> mounted as /qgen."""
    cmd = ["docker", "compose", "-f", str(COMPOSE), "run", "--rm", "-v", f"{work}:/qgen",
           "tpcds-kit", "sh", "-c", "set -e\n" + script]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"dsqgen failed:\n{r.stdout.strip()}\n{r.stderr.strip()}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    for mode in ("validation", "original"):
        sub.add_parser(mode).add_argument("--out", help=f"default: data/queries/{mode}")
    s = sub.add_parser("streams")
    s.add_argument("--sf", type=int, required=True)
    s.add_argument("--streams", type=int, default=5, help="stream 0 + 4 throughput streams")
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--out", help="default: data/queries/sf<SF>")
    args = p.parse_args(argv)

    if not (KIT / "templates.lst").exists():
        sys.exit(f"TPC-DS kit not found: unzip it into {KIT.parent.parent} (see the README)")
    name = f"sf{args.sf}" if args.mode == "streams" else args.mode
    out = Path(args.out) if args.out else REPO / "data" / "queries" / name
    overlay = sorted(OVERLAY.glob("*.tpl")) if args.mode != "original" else []

    work = Path(tempfile.mkdtemp(prefix="qgen-"))
    try:
        shutil.copytree(KIT, work / "templates")
        for f in overlay:
            shutil.copy(f, work / "templates" / f.name)
        if args.mode == "original":   # kit 4.0.0: netezza.tpl lacks the _END define dsqgen needs
            netezza = work / "templates" / "netezza.tpl"
            if "_END" not in netezza.read_text():
                with netezza.open("a") as f:
                    f.write('define _END = "";\n')
        (work / "out").mkdir()
        for d in (work, work / "out"):
            os.chmod(d, 0o777)   # the container runs as another user id on some machines

        if args.mode == "streams":
            run_in_kit(work, f"dsqgen -DIRECTORY /qgen/templates -INPUT /qgen/templates/templates.lst "
                             f"-DIALECT clickhouse -SCALE {args.sf} -STREAMS {args.streams} "
                             f"-RNGSEED {args.seed} -OUTPUT_DIR /qgen/out > /dev/null 2>&1 || true")
        else:
            dialect = "netezza" if args.mode == "original" else "clickhouse"
            run_in_kit(work, PER_TEMPLATE.format(dialect=dialect))

        files = sorted((work / "out").glob("*.sql"))
        expected = args.streams if args.mode == "streams" else 99
        if len(files) != expected:
            sys.exit(f"dsqgen wrote {len(files)} files instead of {expected}")
        out.mkdir(parents=True, exist_ok=True)
        rewritten = 0
        for f in files:
            text = f.read_text(encoding="utf-8")
            if args.mode != "original":
                new = rewrite(text)
                rewritten += new != text
                text = new
                markers, want = len(START.findall(text)), 99 if args.mode == "streams" else 1
                if markers != want:
                    sys.exit(f"{f.name}: {markers} query markers instead of {want}")
            (out / f.name).write_text(text, encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"{len(files)} files in {out}")
    if args.mode != "original":
        print(f"overlay: {', '.join(f.name for f in overlay)}; 'N days' rewritten in {rewritten} files")


if __name__ == "__main__":
    main()
