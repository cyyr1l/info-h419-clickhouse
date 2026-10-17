#!/usr/bin/env python3
"""TPC-DS benchmark harness for ClickHouse (Part I). Python standard library only.

Implements docs/benchmark-protocol.md: runs query streams over the ClickHouse HTTP
interface and writes, to part1-tpcds/results/sf<SF>/<run_id>/, one CSV per test
(one row per SQL statement), environment.json and summary.json.

Commands (from the repo root, with ClickHouse running: cd docker && docker compose up -d):
  validate    run each query once and save its result as CSV, for scripts/compare.py
  load        run a load command, then OPTIMIZE ... FINAL every table (T_Load)
  power       power test: one stream, one query at a time (--cold, --repeat)
  throughput  throughput test: several streams in parallel
  campaign    load (optional), power, throughput, 1 cold + 3 warm power runs

Examples:
  python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries <dir of qNN.sql> --only 26-50 --out results/clickhouse_sf1
  python3 part1-tpcds/scripts/harness.py power --sf 1 --stream <streams dir>/query_0.sql
  python3 part1-tpcds/scripts/harness.py campaign --sf 10 --streams-dir <dir with query_0..4.sql> --load-cmd "<loader>"
"""
import argparse
import csv
import datetime as dt
import hashlib
import http.client
import json
import math
import os
import platform
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = REPO / "part1-tpcds" / "settings.json"
DEFAULT_RESULTS = REPO / "part1-tpcds" / "results"

START = re.compile(r"^-- start query (\d+) in stream (\d+) using template query(\d+)\.tpl[ \t]*$", re.M)
END = re.compile(r"^-- end query \d+ in stream \d+ using template query\d+\.tpl[ \t]*$", re.M)

FIELDS = ["run_id", "sf", "test", "repeat", "stream", "position", "query", "part", "query_id",
          "start_ts", "elapsed_s", "server_ms", "read_rows", "read_bytes", "peak_memory_bytes",
          "result_rows", "status", "error"]
LOAD_FIELDS = ["run_id", "sf", "table", "rows", "parts", "bytes_on_disk", "compressed_bytes",
               "uncompressed_bytes", "optimize_s"]

TIMEOUT_CODES = {159, 160}   # TIMEOUT_EXCEEDED, TOO_SLOW
MEMORY_CODES = {241}         # MEMORY_LIMIT_EXCEEDED


# ---------------------------------------------------------------- queries

@dataclass
class Query:
    position: int       # position in the stream (= template number for a directory of qNN.sql)
    template: int       # TPC-DS template number, 1..99
    statements: list    # 2 statements for templates 14, 23, 24, 39


def split_statements(sql):
    """Split on ';' and drop full-line comments; TPC-DS has no ';' inside literals."""
    out = []
    for chunk in sql.split(";"):
        code = "\n".join(line for line in chunk.splitlines()
                         if not line.lstrip().startswith("--")).strip()
        if code:
            out.append(code)
    return out


def parse_stream(text):
    """Queries of a dsqgen stream written with the clickhouse dialect (start/end markers)."""
    starts = list(START.finditer(text))
    queries = []
    for i, m in enumerate(starts):
        stop = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        end = END.search(text, m.end(), stop)
        body = text[m.end():end.start() if end else stop]
        queries.append(Query(int(m.group(1)), int(m.group(3)), split_statements(body)))
    return queries


def stream_number(text):
    m = START.search(text)
    return int(m.group(2)) if m else None


def template_of(path):
    m = re.match(r"q(\d+)$", Path(path).stem)
    if not m:
        raise ValueError(f"cannot read a template number from {path} (expected qNN.sql)")
    return int(m.group(1))


def load_queries(paths):
    """Queries from stream files (with markers), qNN.sql files, or directories of qNN.sql.

    In a directory, the position of a query is its template number (template order)."""
    queries = []
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.glob("q[0-9]*.sql"), key=template_of):
                n, text = template_of(f), f.read_text(encoding="utf-8")
                parsed = parse_stream(text)
                stmts = [s for q in parsed for s in q.statements] if parsed else split_statements(text)
                queries.append(Query(n, n, stmts))
        else:
            text = p.read_text(encoding="utf-8")
            if START.search(text):
                queries += parse_stream(text)
            else:
                n = template_of(p)
                queries.append(Query(n, n, split_statements(text)))
    return queries


def parse_only(spec):
    """'26-28,30' -> {26, 27, 28, 30}; None -> None (all queries)."""
    if not spec:
        return None
    out = set()
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def result_name(template, part, nparts):
    """File name used by the reference answers: q05, q14_1, q14_2."""
    return f"q{template:02d}" + (f"_{part}" if nparts > 1 else "")


# ---------------------------------------------------------------- settings and metrics

def load_settings(path):
    """Merge the sections of settings.json ('about' and other non-dict keys are ignored)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    merged = {}
    for section in ("sql_compatibility", "benchmark"):
        for key, value in doc.get(section, {}).items():
            if key in merged:
                raise ValueError(f"setting {key} appears in two sections of {path}")
            merged[key] = value
    return merged


def qphds(sf, sq, t_power_s, t_tt_s, t_dm_s, t_load_s):
    """Official QphDS@SF (spec 7.6.3). t_tt_s = T_TT1 + T_TT2, t_dm_s = T_DM1 + T_DM2."""
    h = 3600.0
    t_pt, t_tt, t_dm = sq * t_power_s / h, t_tt_s / h, t_dm_s / h
    t_ld = 0.01 * sq * t_load_s / h
    return math.floor(sf * 99 * sq / (t_pt * t_tt * t_dm * t_ld) ** 0.25)


def simplified_metric(sf, sq, t_power_s, t_tt1_s, t_load_s):
    """Our metric without data maintenance (protocol, section 6): cube root of 3 terms."""
    h = 3600.0
    t_pt, t_tt, t_ld = sq * t_power_s / h, t_tt1_s / h, 0.01 * sq * t_load_s / h
    return math.floor(sf * 99 * sq / (t_pt * t_tt * t_ld) ** (1 / 3))


def classify(code):
    if code in TIMEOUT_CODES:
        return "timeout"
    if code in MEMORY_CODES:
        return "memory"
    return "error"


def new_query_id(*parts):
    return "-".join(map(str, parts + (uuid.uuid4().hex[:6],)))


# ---------------------------------------------------------------- ClickHouse over HTTP

@dataclass
class Result:
    status: str          # ok / error / timeout / memory
    elapsed_s: float
    start_ts: str
    client_rows: int
    error: str = ""
    body: bytes = b""


class ClickHouse:
    """One HTTP session (keep-alive connection). Not thread-safe: one per stream."""

    def __init__(self, host, port, user, password, database, settings, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}
        self.database, self.settings = database, dict(settings)
        self.conn = None

    def close(self):
        if self.conn:
            self.conn.close()
        self.conn = None

    def _send(self, url, sql):
        fresh = self.conn is None
        if fresh:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            self.conn.request("POST", url, body=sql.encode("utf-8"), headers=self.headers)
            return self.conn.getresponse()
        except (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError):
            if fresh:
                raise
            self.close()   # the server closed an idle keep-alive connection: the query never ran
            return self._send(url, sql)

    def execute(self, sql, query_id, fmt="TabSeparated", settings=None, keep_body=False):
        params = {"database": self.database, "query_id": query_id, "default_format": fmt,
                  "wait_end_of_query": 1, **self.settings, **(settings or {})}
        url = "/?" + urlencode(params)
        start_ts = dt.datetime.now().isoformat(timespec="milliseconds")
        t0 = time.perf_counter()
        try:
            resp = self._send(url, sql)
            body = resp.read()
        except (socket.timeout, TimeoutError):
            self.close()
            return Result("timeout", time.perf_counter() - t0, start_ts, 0, "client timeout")
        except (OSError, http.client.HTTPException) as e:
            self.close()
            return Result("error", time.perf_counter() - t0, start_ts, 0, f"connection: {e}")
        elapsed = time.perf_counter() - t0
        if resp.status == 200:
            rows = body.count(b"\n") - (1 if fmt.endswith("WithNames") and body else 0)
            return Result("ok", elapsed, start_ts, max(rows, 0), "", body if keep_body else b"")
        code = int(resp.getheader("X-ClickHouse-Exception-Code") or 0)
        text = body.decode("utf-8", "replace").strip()
        msg = text.splitlines()[0][:300] if text else f"HTTP {resp.status}"
        return Result(classify(code), elapsed, start_ts, 0, f"{code}: {msg}")

    def query_rows(self, sql):
        """Run a small internal query and return its rows as dicts (JSONEachRow)."""
        r = self.execute(sql, new_query_id("harness"), fmt="JSONEachRow", keep_body=True)
        if r.status != "ok":
            raise RuntimeError(f"{sql[:80]}...: {r.error}")
        return [json.loads(line) for line in r.body.decode("utf-8").splitlines() if line]

    def server_stats(self, query_ids):
        """Server-side values of finished queries, from system.query_log."""
        stats = {}
        ids = sorted(set(query_ids))
        if not ids:
            return stats
        self.execute("SYSTEM FLUSH LOGS", new_query_id("harness"))
        for i in range(0, len(ids), 500):
            id_list = ",".join("'" + q.replace("'", "") + "'" for q in ids[i:i + 500])
            for row in self.query_rows(
                    "SELECT query_id, query_duration_ms, read_rows, read_bytes, memory_usage, "
                    "result_rows, exception_code FROM system.query_log "
                    f"WHERE event_date >= yesterday() AND query_id IN ({id_list}) "
                    "AND type != 'QueryStart' ORDER BY event_time_microseconds"):
                stats[row["query_id"]] = {
                    "server_ms": int(row["query_duration_ms"]), "read_rows": int(row["read_rows"]),
                    "read_bytes": int(row["read_bytes"]), "peak_memory_bytes": int(row["memory_usage"]),
                    "result_rows": int(row["result_rows"]), "exception_code": int(row["exception_code"])}
        return stats


# ---------------------------------------------------------------- environment

def sh(cmd, check=False):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        if check:
            raise
        return ""
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def read_first(path, pattern):
    try:
        m = re.search(pattern, Path(path).read_text(), re.M)
        return m.group(1).strip() if m else None
    except OSError:
        return None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture_environment(ch, args, test, files):
    others = [n for n in sh(["docker", "ps", "--format", "{{.Names}}"]).splitlines()
              if n and n != args.container]
    if others:
        print(f"WARNING: {len(others)} other container(s) running ({', '.join(others[:5])}...). "
              "ClickHouse's memory limit depends on free memory: stop them for measured runs "
              "(protocol, section 1).", file=sys.stderr)
    server = {r["name"]: r["value"] for r in ch.query_rows(
        "SELECT name, value FROM system.server_settings WHERE name IN "
        "('max_server_memory_usage', 'max_server_memory_usage_to_ram_ratio', "
        "'memory_worker_dynamic_hard_limit')")}
    mem_kb = read_first("/proc/meminfo", r"^MemTotal:\s+(\d+)")
    return {
        "test": test,
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "argv": sys.argv,
        "host": {
            "platform": platform.platform(),
            "cpu": read_first("/proc/cpuinfo", r"^model name\s*:\s*(.+)$"),
            "logical_cpus": os.cpu_count(),
            "memory_gib": round(int(mem_kb) / 2**20, 2) if mem_kb else None,
            "wsl": "microsoft" in platform.release().lower(),
            "python": platform.python_version(),
        },
        "docker": {"server": sh(["docker", "version", "--format", "{{.Server.Version}}"]),
                   "other_running_containers": others},
        "clickhouse": {
            "version": ch.query_rows("SELECT version() AS v")[0]["v"],
            "server_settings": server,
            "database": args.database,
            "tables": ch.query_rows(
                "SELECT name, total_rows, total_bytes FROM system.tables "
                f"WHERE database = '{args.database}' ORDER BY name"),
        },
        "settings_profile": ch.settings,
        "git": {"commit": sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]),
                "branch": sh(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"]),
                "dirty": bool(sh(["git", "-C", str(REPO), "status", "--porcelain"]))},
        "query_files": {str(f): sha256(f) for f in files if Path(f).is_file()},
    }


def cold_reset(container, ch, wait_s=180):
    """Stop ClickHouse, drop the Linux page cache (shared WSL2 kernel), start, wait healthy."""
    print(f"cold reset: stopping {container}, dropping the page cache, starting it again")
    ch.close()
    sh(["docker", "stop", container], check=True)
    sh(["docker", "run", "--rm", "--privileged", "alpine:3.20", "sh", "-c",
        "sync; echo 3 > /proc/sys/vm/drop_caches"], check=True)
    sh(["docker", "start", container], check=True)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        healthy = sh(["docker", "inspect", "-f", "{{.State.Health.Status}}", container]) == "healthy"
        if healthy and ch.execute("SELECT 1", new_query_id("harness")).status == "ok":
            return
        time.sleep(1)
    raise RuntimeError(f"{container} not healthy after {wait_s} s")


# ---------------------------------------------------------------- runs

def fmt_sf(sf):
    return f"{sf:g}"


class Run:
    """results/sf<SF>/<run_id>/: one CSV per test, environment.json, summary.json."""

    def __init__(self, args):
        self.args = args
        self.run_id = args.run_id or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = Path(args.results) / f"sf{fmt_sf(args.sf)}" / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def append_csv(self, name, fields, rows):
        path = self.dir / f"{name}.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerows(rows)

    def _update_json(self, name, update):
        path = self.dir / name
        doc = json.loads(path.read_text()) if path.exists() else {}
        update(doc)
        path.write_text(json.dumps(doc, indent=2) + "\n")

    def add_environment(self, env):
        self._update_json("environment.json",
                          lambda d: d.setdefault("captures", []).append(env))

    def add_summary(self, key, value, append=False):
        def upd(d):
            d.update(run_id=self.run_id, sf=self.args.sf)
            if append:
                d.setdefault(key, []).append(value)
            else:
                d[key] = value
        self._update_json("summary.json", upd)

    def summary(self):
        path = self.dir / "summary.json"
        return json.loads(path.read_text()) if path.exists() else {}


def run_stream(ch, queries, ctx, stream, repeat, barrier=None, verbose=True):
    """Run the queries of one stream sequentially. Returns (rows, t_first_send, t_last_receive)."""
    rows = []
    if barrier:
        barrier.wait()
    t_first = time.perf_counter()
    n = len(queries)
    for i, q in enumerate(queries, 1):
        for part, sql in enumerate(q.statements, 1):
            qid = new_query_id(ctx.run_id, ctx.test, f"r{repeat}", f"s{stream}",
                               f"p{q.position:02d}", f"q{q.template:02d}", part)
            r = ch.execute(sql, qid)
            rows.append({"run_id": ctx.run_id, "sf": ctx.args.sf, "test": ctx.test, "repeat": repeat,
                         "stream": stream, "position": q.position, "query": q.template, "part": part,
                         "query_id": qid, "start_ts": r.start_ts, "elapsed_s": round(r.elapsed_s, 4),
                         "result_rows": r.client_rows, "status": r.status, "error": r.error})
            if verbose:
                label = f"q{q.template:02d}" + (f".{part}" if len(q.statements) > 1 else "  ")
                print(f"[{ctx.test} r{repeat} s{stream}] {i:3d}/{n} {label} "
                      f"{r.elapsed_s:9.3f}s {r.status:7s} {r.error[:100]}", flush=True)
    return rows, t_first, time.perf_counter()


def add_server_stats(ch, rows):
    stats = ch.server_stats([r["query_id"] for r in rows])
    for r in rows:
        s = stats.get(r["query_id"])
        if not s:
            continue
        r.update({k: s[k] for k in ("server_ms", "read_rows", "read_bytes", "peak_memory_bytes",
                                    "result_rows")})
        if r["status"] == "ok" and s["exception_code"]:
            r["status"], r["error"] = classify(s["exception_code"]), f"{s['exception_code']}: (query_log)"


def failures(rows):
    return sum(r["status"] != "ok" for r in rows)


class Ctx:
    def __init__(self, args, run, test):
        self.args, self.run_id, self.test = args, run.run_id, test


def power_test(args, run, ch, stream_file, test, repeats, cold):
    text = Path(stream_file).read_text(encoding="utf-8")
    queries = load_queries([stream_file])
    stream = stream_number(text) or 0
    run.add_environment(capture_environment(ch, args, test, [stream_file]))
    results = []
    for rep in range(1, repeats + 1):
        if cold:
            cold_reset(args.container, ch)
        rows, t0, t1 = run_stream(ch, queries, Ctx(args, run, test), stream, rep, verbose=not args.quiet)
        add_server_stats(ch, rows)
        run.append_csv(test, FIELDS, rows)
        res = {"repeat": rep, "stream": stream, "t_power_s": round(t1 - t0, 3),
               "queries": len(queries), "failures": failures(rows)}
        run.add_summary(test, res, append=True)
        print(f"== {test} run {rep}: T_Power = {t1 - t0:.1f} s, failures = {res['failures']}")
        results.append(res)
    return results


def throughput_test(args, run, stream_files, test="throughput"):
    parsed = []
    for i, f in enumerate(stream_files, 1):
        text = Path(f).read_text(encoding="utf-8")
        parsed.append((stream_number(text) or i, load_queries([f])))
    probe = connect(args)
    run.add_environment(capture_environment(probe, args, test, stream_files))
    barrier = threading.Barrier(len(parsed))
    outcome = {}

    def worker(stream, queries):
        ch = connect(args)
        outcome[stream] = run_stream(ch, queries, Ctx(args, run, test), stream, 1, barrier,
                                     verbose=not args.quiet)
        ch.close()

    threads = [threading.Thread(target=worker, args=p) for p in parsed]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = [r for s in sorted(outcome) for r in outcome[s][0]]
    t_tt = max(o[2] for o in outcome.values()) - min(o[1] for o in outcome.values())
    add_server_stats(probe, rows)
    probe.close()
    run.append_csv(test, FIELDS, rows)
    res = {"t_tt1_s": round(t_tt, 3), "streams": len(parsed), "failures": failures(rows),
           "per_stream_s": {s: round(o[2] - o[1], 3) for s, o in sorted(outcome.items())}}
    run.add_summary(test, res, append=True)
    print(f"== {test}: T_TT1 = {t_tt:.1f} s with {len(parsed)} streams, failures = {res['failures']}")
    return res


def load_test(args, run, command):
    ch = connect(args, timeout=6 * 3600)   # OPTIMIZE FINAL on big tables can take long
    t0 = time.perf_counter()
    subprocess.run(command, check=True)
    t1 = time.perf_counter()
    tables = [r["name"] for r in ch.query_rows(
        f"SELECT name FROM system.tables WHERE database = '{args.database}' "
        "AND engine LIKE '%MergeTree%' ORDER BY name")]
    optimize_s = {}
    for t in tables:
        r = ch.execute(f"OPTIMIZE TABLE {args.database}.{t} FINAL", new_query_id(run.run_id, "optimize", t))
        if r.status != "ok":
            raise RuntimeError(f"OPTIMIZE {t}: {r.error}")
        optimize_s[t] = round(r.elapsed_s, 3)
    t2 = time.perf_counter()
    parts = ch.query_rows(
        "SELECT table, sum(rows) AS rows, count() AS parts, sum(bytes_on_disk) AS bytes_on_disk, "
        "sum(data_compressed_bytes) AS compressed_bytes, "
        "sum(data_uncompressed_bytes) AS uncompressed_bytes FROM system.parts "
        f"WHERE database = '{args.database}' AND active GROUP BY table ORDER BY table")
    rows = [{"run_id": run.run_id, "sf": args.sf, "optimize_s": optimize_s.get(p["table"]), **p}
            for p in parts]
    run.append_csv("load", LOAD_FIELDS, rows)
    run.add_environment(capture_environment(ch, args, "load", []))
    res = {"t_load_s": round(t2 - t0, 3), "load_s": round(t1 - t0, 3),
           "optimize_s": round(t2 - t1, 3), "tables": len(tables),
           "rows": sum(int(p["rows"]) for p in parts)}
    run.add_summary("load", res)
    print(f"== load: T_Load = {t2 - t0:.1f} s (load {t1 - t0:.1f} s + optimize {t2 - t1:.1f} s)")
    return res


def connect(args, timeout=None, database=None):
    settings = load_settings(args.settings)
    limit = int(settings.get("max_execution_time", 0) or 0)
    return ClickHouse(args.host, args.port, args.user, args.password, database or args.database,
                      settings, timeout or (limit + 60 if limit else 3600))


def preflight_settings(args):
    """ClickHouse answers and accepts every setting of the profile (before a load: no database yet)."""
    ch = connect(args, database="default")
    r = ch.execute("SELECT 1", new_query_id("harness"))
    ch.close()
    if r.status != "ok":
        sys.exit(f"ClickHouse on {args.host}:{args.port} rejected a test query "
                 f"(is it running, and are all settings in {args.settings} valid?): {r.error}")


def preflight(args):
    preflight_settings(args)
    ch = connect(args)
    if not ch.query_rows(f"SELECT 1 AS ok FROM system.databases WHERE name = '{args.database}'"):
        sys.exit(f"database {args.database} does not exist (load the data first, or use --database)")
    return ch


# ---------------------------------------------------------------- commands

def cmd_validate(args):
    ch = preflight(args)
    only = parse_only(args.only)
    queries = [q for q in load_queries(args.queries) if only is None or q.template in only]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    status = []
    for q in queries:
        for part, sql in enumerate(q.statements, 1):
            name = result_name(q.template, part, len(q.statements))
            # NULL as "" (quoted): an unquoted empty single-column row is a blank line,
            # which pandas skips (e.g. Q23 part 1, a sum over no rows).
            r = ch.execute(sql, new_query_id("validate", name), fmt="CSVWithNames",
                           settings={"format_csv_null_representation": '""'}, keep_body=True)
            target = out / f"{name}.csv"
            if r.status == "ok":
                target.write_bytes(r.body)
            elif target.exists():
                target.unlink()   # never compare a stale result
            status.append({"query": name, "status": r.status, "elapsed_s": round(r.elapsed_s, 3),
                           "rows": r.client_rows, "error": r.error})
            print(f"{name:7s} {r.status:7s} {r.elapsed_s:8.3f}s {r.client_rows:6d} rows  {r.error[:120]}")
    with (out / "harness_status.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["query", "status", "elapsed_s", "rows", "error"])
        w.writeheader()
        w.writerows(status)
    print(f"\n{sum(s['status'] == 'ok' for s in status)}/{len(status)} statements ran. Compare with:\n"
          f"  python3 part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1 {out}")


def cmd_load(args):
    if not args.command:
        sys.exit("give the load command after --, e.g. harness.py load --sf 1 -- ./load.sh 1")
    command = args.command[1:] if args.command[0] == "--" else args.command
    preflight_settings(args)
    load_test(args, Run(args), command)


def cmd_power(args):
    ch = preflight(args)
    run = Run(args)
    test = args.test or ("power_cold" if args.cold else "power")
    power_test(args, run, ch, args.stream, test, args.repeat, args.cold)
    print(f"results: {run.dir}")


def cmd_throughput(args):
    preflight(args)
    run = Run(args)
    throughput_test(args, run, args.streams)
    print(f"results: {run.dir}")


def cmd_campaign(args):
    d = Path(args.streams_dir)
    s0 = d / "query_0.sql"
    others = sorted((f for f in d.glob("query_*.sql") if f != s0),
                    key=lambda f: int(re.search(r"(\d+)$", f.stem).group(1)))
    if not s0.exists() or len(others) < 4:
        sys.exit(f"{d} must contain query_0.sql (power) and at least 4 more streams (throughput)")
    others = others[:args.sq]
    run = Run(args)
    load = None
    if args.load_cmd:
        preflight_settings(args)
        load = load_test(args, run, shlex.split(args.load_cmd))
    ch = preflight(args)
    power = power_test(args, run, ch, s0, "power", 1, cold=False)[0]
    tput = throughput_test(args, run, others)
    power_test(args, run, ch, s0, "power_cold", 1, cold=True)
    power_test(args, run, ch, s0, "power_warm", args.warm, cold=False)
    if load:
        run.add_summary("simplified_metric", simplified_metric(
            args.sf, len(others), power["t_power_s"], tput["t_tt1_s"], load["t_load_s"]))
    print(f"campaign done: {run.dir}\n{json.dumps(run.summary(), indent=2)}")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--sf", type=float, required=True, help="scale factor of the loaded data")
        sp.add_argument("--database", help="default: tpcds_sf<SF>")
        sp.add_argument("--host", default="localhost")
        sp.add_argument("--port", type=int, default=8123)
        sp.add_argument("--user", default="default")
        sp.add_argument("--password", default=os.environ.get("CLICKHOUSE_PASSWORD", "infoh419"))
        sp.add_argument("--settings", default=str(DEFAULT_SETTINGS), help="settings profile (JSON)")
        sp.add_argument("--results", default=str(DEFAULT_RESULTS))
        sp.add_argument("--run-id", help="reuse a run directory (default: new timestamp)")
        sp.add_argument("--container", default="infoh419-clickhouse")
        sp.add_argument("--quiet", action="store_true", help="no line per query")
        return sp

    v = common(sub.add_parser("validate", help="run queries once, save results as CSV"))
    v.add_argument("--queries", nargs="+", required=True, help="dir of qNN.sql, qNN.sql files or streams")
    v.add_argument("--only", help="templates to run, e.g. 26-50 or 30,47")
    v.add_argument("--out", required=True, help="folder for qNN.csv (as in reference/sf1)")
    v.set_defaults(func=cmd_validate)

    ld = common(sub.add_parser("load", help="time a load command + OPTIMIZE FINAL (T_Load)"))
    ld.add_argument("command", nargs=argparse.REMAINDER, help="-- <load command ...>")
    ld.set_defaults(func=cmd_load)

    pw = common(sub.add_parser("power", help="power test on one stream"))
    pw.add_argument("--stream", required=True, help="stream file (query_0.sql) or qNN.sql / dir")
    pw.add_argument("--repeat", type=int, default=1)
    pw.add_argument("--cold", action="store_true", help="cold reset before each repetition")
    pw.add_argument("--test", help="test name in the results (default power / power_cold)")
    pw.set_defaults(func=cmd_power)

    tp = common(sub.add_parser("throughput", help="throughput test: streams in parallel"))
    tp.add_argument("--streams", nargs="+", required=True, help="stream files (query_1.sql ...)")
    tp.set_defaults(func=cmd_throughput)

    cp = common(sub.add_parser("campaign", help="the whole protocol for one SF"))
    cp.add_argument("--streams-dir", required=True, help="folder with query_0.sql ... query_4.sql")
    cp.add_argument("--load-cmd", help="command that creates and loads the tables (timed as T_Load)")
    cp.add_argument("--sq", type=int, default=4, help="throughput streams (default 4)")
    cp.add_argument("--warm", type=int, default=3, help="warm power runs (default 3)")
    cp.set_defaults(func=cmd_campaign)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.database = args.database or f"tpcds_sf{fmt_sf(args.sf).replace('.', '_')}"
    args.func(args)


if __name__ == "__main__":
    main()
