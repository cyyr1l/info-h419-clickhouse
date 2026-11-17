#!/usr/bin/env python3
"""Timing of a TPC-DI Benchmark Run (docs/benchmark-protocol-part2.md, sections 1.1, 4 and 6).

The orchestrator imports this module. It measures, it does not run the ETL:

    import timing
    run = timing.Run(sf=10)                       # results/sf10/<run_id>/
    run.measure_drift("before")                   # 60 s against the Windows clock (section 1.1)
    with run.step("HL", 1, "dimtrade_historical.sql", "DimTrade") as st:
        my_query(sql, query_id=st.query_id())     # EVERY query of the step carries a query_id
    ...
    with run.step("HL", 1, "validation.sql", "DImessages", pcr=True) as st:   # ends each phase
        my_query(validation_sql, query_id=st.query_id())
    run.measure_drift("after")
    run.finish()        # steps.csv, summary.json, environment.json, dimessages.csv, digen_report.txt

What it records:
- Steps (section 4.2): start time (realtime), duration from time.perf_counter() divided by the
  drift factor, status and error, and from system.query_log, matched on the step's query_ids:
  rows and bytes read and written, peak memory.
- Phases (section 4.1): CT0-CT3 are the MessageDateAndTime of the PCR rows in DImessages;
  EH, EI1, EI2 rounded up to 0.1 s.
- Metric (section 4.3): RH, RI1, RI2 from digen_report.txt, TH, TI1, TI2 and TPC_DI_RPS.
- Check (section 4.2): per phase, the monotonic time between the ends of two consecutive phases
  (corrected for drift) must match EH or EI within 1% or 1 s, whichever is larger.

Self-test (needs the ClickHouse container): python3 part2-tpcdi/scripts/timing.py --self-test
Standard library only.
"""

import argparse
import csv
import datetime as dt
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PART2 = REPO / "part2-tpcdi"
STEP_COLUMNS = ["run_id", "sf", "phase", "batch_id", "step", "target_table", "query_id", "start_ts",
                "elapsed_s", "elapsed_raw_s", "read_rows", "read_bytes", "written_rows", "written_bytes",
                "peak_memory_bytes", "status", "error"]
FLOOR_S = 1800          # incremental phases shorter than this count as 1800 s (spec 7.5)
CLOCKSOURCE = Path("/sys/devices/system/clocksource/clocksource0/current_clocksource")


class ClickHouse:
    """Minimal HTTP client for the module's own queries (query_log, DImessages, exports)."""

    def __init__(self, url="http://localhost:8123", user="default", password="infoh419", database=None):
        self.url, self.database = url.rstrip("/"), database
        self.headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}

    def query(self, sql, database=None, query_id=None):
        args = {}
        if database or self.database:
            args["database"] = database or self.database
        if query_id:
            args["query_id"] = query_id
        request = urllib.request.Request(self.url + "/?" + urllib.parse.urlencode(args),
                                         data=sql.encode(), headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                return response.read().decode().strip()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{error.read().decode().strip()[:500]}\n--- in query:\n{sql[:300]}") from None

    def rows(self, sql, database=None):
        text = self.query(sql + " FORMAT JSONEachRow", database)
        return [json.loads(line) for line in text.splitlines() if line]


def measure_drift(seconds=60):
    """Factor between the monotonic clock of WSL (time.perf_counter) and the Windows clock.

    One PowerShell process prints the Windows time (ms), sleeps, prints it again. Each line is
    timestamped when it arrives, so PowerShell's start-up time does not count. Durations measured
    with perf_counter are divided by this factor (protocol, section 1.1). Outside WSL there is no
    Windows clock: the factor is 1.0 and 'source' says so.
    """
    clocksource = CLOCKSOURCE.read_text().strip() if CLOCKSOURCE.is_file() else None
    powershell = shutil.which("powershell.exe")
    if not powershell:
        return {"factor": 1.0, "seconds": 0, "source": "no Windows clock (not WSL)", "clocksource": clocksource}
    script = ("$o = [Console]::Out; $o.WriteLine([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()); $o.Flush(); "
              f"Start-Sleep -Milliseconds {int(seconds * 1000)}; "
              "$o.WriteLine([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()); $o.Flush()")
    process = subprocess.Popen([powershell, "-NoProfile", "-Command", script], stdout=subprocess.PIPE, text=True)
    readings = []
    for line in process.stdout:
        now = time.perf_counter()
        if line.strip().isdigit():
            readings.append((now, int(line)))
    process.wait()
    if len(readings) != 2:
        raise RuntimeError(f"Windows clock: expected 2 readings, got {readings}")
    (m1, w1), (m2, w2) = readings
    return {"factor": round((m2 - m1) / ((w2 - w1) / 1000), 6), "seconds": round((w2 - w1) / 1000, 3),
            "monotonic_s": round(m2 - m1, 6), "source": "PowerShell [DateTimeOffset]::UtcNow",
            "clocksource": clocksource, "measured_at": dt.datetime.now().isoformat(timespec="seconds")}


def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return ""


def capture_environment(ch, container="infoh419-clickhouse"):
    """As in Part I (host, versions, memory limit, other containers, git commit), plus the clocksource."""
    others = [n for n in sh(["docker", "ps", "--format", "{{.Names}}"]).splitlines() if n and n != container]
    mem_kb = re.search(r"^MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text(), re.M) if Path("/proc/meminfo").is_file() else None
    cpu = re.search(r"^model name\s*:\s*(.+)$", Path("/proc/cpuinfo").read_text(), re.M) if Path("/proc/cpuinfo").is_file() else None
    return {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "argv": sys.argv,
        "host": {"platform": platform.platform(), "cpu": cpu.group(1).strip() if cpu else None,
                 "logical_cpus": os.cpu_count(), "memory_gib": round(int(mem_kb.group(1)) / 2**20, 2) if mem_kb else None,
                 "wsl": "microsoft" in platform.release().lower(), "python": platform.python_version(),
                 "clocksource": CLOCKSOURCE.read_text().strip() if CLOCKSOURCE.is_file() else None},
        "docker": {"server": sh(["docker", "version", "--format", "{{.Server.Version}}"]),
                   "other_running_containers": others},
        "clickhouse": {"version": ch.query("SELECT version()"),
                       "server_settings": {r["name"]: r["value"] for r in ch.rows(
                           "SELECT name, value FROM system.server_settings WHERE name IN "
                           "('max_server_memory_usage', 'max_server_memory_usage_to_ram_ratio')")}},
        "git": {"commit": sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]),
                "branch": sh(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"]),
                "dirty": bool(sh(["git", "-C", str(REPO), "status", "--porcelain"]))},
    }


def digen_rows(report_path):
    """RH, RI1, RI2: the record totals of Batch1-3 in digen_report.txt (spec 7.5.2.2, 7.5.3.2)."""
    totals = {int(b): int(n) for b, n in re.findall(r"TotalRecords for Batch(\d): (\d+)", Path(report_path).read_text())}
    if sorted(totals) != [1, 2, 3]:
        raise ValueError(f"{report_path}: no record totals for the 3 batches")
    return totals


def metric(e, rows):
    """TPC_DI_RPS = trunc(sqrt(TH * min(TI1, TI2))), with the 1800 s floor (protocol, section 4.3)."""
    th = rows[1] / e["EH"]
    ti1, ti2 = rows[2] / max(e["EI1"], FLOOR_S), rows[3] / max(e["EI2"], FLOOR_S)
    return {"RH": rows[1], "RI1": rows[2], "RI2": rows[3], "TH": round(th, 3), "TI1": round(ti1, 3),
            "TI2": round(ti2, 3), "TI1_unfloored": round(rows[2] / e["EI1"], 3),
            "TI2_unfloored": round(rows[3] / e["EI2"], 3), "TPC_DI_RPS": math.trunc(math.sqrt(th * min(ti1, ti2)))}


def round_up(seconds):
    """Reported to 0.1 s and rounded up (spec 7.1.1)."""
    return math.ceil(round(seconds * 10, 6)) / 10


class Step:
    def __init__(self, run, index, phase, batch_id, step, target_table):
        self.run, self.phase, self.batch_id, self.step, self.target_table = run, phase, batch_id, step, target_table
        self.prefix = f"{run.run_id}-{index:03d}-"     # unique per step: no step's prefix starts another's
        self.query_ids, self.status, self.error = [], "ok", ""

    def query_id(self):
        """A new query_id for one query of this step. Pass it to ClickHouse (HTTP parameter query_id)."""
        qid = f"{self.prefix}{len(self.query_ids) + 1}"
        self.query_ids.append(qid)
        return qid


class Run:
    def __init__(self, sf, ch=None, results_root=PART2 / "results", run_id=None, data_dir=None):
        self.sf, self.ch = sf, ch or ClickHouse(database=f"tpcdi_sf{sf}")
        self.run_id = run_id or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = Path(results_root) / f"sf{sf}" / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = Path(data_dir) if data_dir else REPO / "data" / "tpcdi" / f"sf{sf}"
        self.steps, self.drift = [], {}

    def measure_drift(self, when, seconds=60):
        self.drift[when] = measure_drift(seconds)
        print(f"drift {when}: {self.drift[when]['factor']} ({self.drift[when]['source']})", flush=True)
        return self.drift[when]

    def factor(self):
        """Mean of the drift factors measured before and after the run (1.0 if none)."""
        values = [d["factor"] for d in self.drift.values()]
        return sum(values) / len(values) if values else 1.0

    @contextmanager
    def step(self, phase, batch_id, step, target_table="", pcr=False):
        """Time one step. pcr=True marks the step that writes the phase's PCR (validation.sql)."""
        st = Step(self, len(self.steps) + 1, phase, batch_id, step, target_table)
        st.pcr = pcr
        st.start_ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
        st.t0 = time.perf_counter()
        try:
            yield st
        except BaseException as error:
            st.status, st.error = "error", f"{type(error).__name__}: {error}"[:500]
            raise                                # a failed step stops the run (protocol, section 5)
        finally:
            st.t1 = time.perf_counter()
            self.steps.append(st)

    def phase_times(self):
        """CT0-CT3 from the PCR rows of DImessages, and EH, EI1, EI2 (protocol, section 4.1)."""
        pcr = self.ch.rows("SELECT BatchID, toString(MessageDateAndTime) AS ct, count() OVER (PARTITION BY BatchID) AS n "
                           "FROM DImessages WHERE MessageType = 'PCR' ORDER BY BatchID")
        ct = {int(r["BatchID"]): dt.datetime.fromisoformat(r["ct"]) for r in pcr}
        problems = [f"BatchID {r['BatchID']}: {r['n']} PCR rows" for r in pcr if int(r["n"]) != 1]
        result = {f"CT{b}": ct[b].isoformat(timespec="milliseconds") for b in sorted(ct)}
        names = {1: "EH", 2: "EI1", 3: "EI2"}
        for b, name in names.items():
            if b in ct and b - 1 in ct:
                result[name] = round_up((ct[b] - ct[b - 1]).total_seconds())
        return result, problems

    def _query_log(self):
        """Per step: sums and peak from system.query_log, matched on the step's query_ids."""
        ids = [q for st in self.steps for q in st.query_ids]
        stats = {}
        if not ids:
            return stats
        self.ch.query("SYSTEM FLUSH LOGS")
        for i in range(0, len(ids), 500):
            id_list = ",".join(f"'{q}'" for q in ids[i:i + 500])
            for r in self.ch.rows("SELECT query_id, read_rows, read_bytes, written_rows, written_bytes, memory_usage "
                                  f"FROM system.query_log WHERE event_date >= yesterday() AND query_id IN ({id_list}) "
                                  "AND type != 'QueryStart'"):
                stats[r["query_id"]] = r
        return stats

    def _gap_check(self, phases):
        """Monotonic time between the ends of two consecutive phases vs EH/EI (protocol, section 4.2)."""
        ends = {st.batch_id: st.t1 for st in self.steps if st.pcr}   # end of the step that wrote the PCR
        checks = []
        for b, name in {1: "EH", 2: "EI1", 3: "EI2"}.items():
            if name in phases and b in ends and b - 1 in ends:
                measured = (ends[b] - ends[b - 1]) / self.factor()
                tolerance = max(0.01 * phases[name], 1.0)
                checks.append({"phase": name, "official_s": phases[name], "steps_and_gaps_s": round(measured, 2),
                               "ok": abs(measured - phases[name]) <= tolerance + 0.1})   # + rounding to 0.1 s
        return checks

    def finish(self, database_tables=True, container="infoh419-clickhouse"):
        """Write steps.csv, summary.json, environment.json, dimessages.csv and digen_report.txt."""
        factor, stats = self.factor(), self._query_log()
        with (self.dir / "steps.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, STEP_COLUMNS)
            writer.writeheader()
            for st in self.steps:
                rows = [stats[q] for q in st.query_ids if q in stats]
                writer.writerow({
                    "run_id": self.run_id, "sf": self.sf, "phase": st.phase, "batch_id": st.batch_id,
                    "step": st.step, "target_table": st.target_table, "query_id": st.prefix + "*",
                    "start_ts": st.start_ts, "elapsed_s": round((st.t1 - st.t0) / factor, 3),
                    "elapsed_raw_s": round(st.t1 - st.t0, 3),
                    **{k: sum(int(r[k]) for r in rows) for k in ("read_rows", "read_bytes", "written_rows", "written_bytes")},
                    "peak_memory_bytes": max((int(r["memory_usage"]) for r in rows), default=0),
                    "status": st.status, "error": st.error})
        summary = {"run_id": self.run_id, "sf": self.sf, "drift_factor_used": round(factor, 6), "steps": len(self.steps),
                   "failed_steps": sum(st.status != "ok" for st in self.steps)}
        if database_tables:
            phases, problems = self.phase_times()
            summary.update(phases)
            summary["pcr_problems"] = problems
            summary["gap_check"] = self._gap_check(phases)
            report = self.data_dir / "digen_report.txt"
            if report.is_file():
                shutil.copy(report, self.dir / "digen_report.txt")
                if all(k in phases for k in ("EH", "EI1", "EI2")):
                    summary.update(metric(phases, digen_rows(report)))
            (self.dir / "dimessages.csv").write_text(
                self.ch.query("SELECT * FROM DImessages ORDER BY MessageDateAndTime FORMAT CSVWithNames") + "\n")
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        environment = capture_environment(self.ch, container)
        environment["drift"] = self.drift
        (self.dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
        print(f"results: {self.dir}")
        return summary


def self_test():
    """Fake run on a throwaway database: 4 phases with timed steps, then the outputs are checked."""
    ch = ClickHouse()
    db = "timing_selftest_" + dt.datetime.now().strftime("%H%M%S")
    ch.query(f"CREATE DATABASE {db}")
    ch.database = db
    ch.query("CREATE TABLE DImessages (MessageDateAndTime DateTime64(3), BatchID UInt32, MessageSource Nullable(String), "
             "MessageText String, MessageType String, MessageData Nullable(String)) ENGINE = MergeTree ORDER BY tuple()")
    ch.query("CREATE TABLE t (x UInt64) ENGINE = MergeTree ORDER BY x")
    tmp = Path(tempfile.mkdtemp(prefix="timing_selftest_"))
    run = Run(sf=10, ch=ch, results_root=tmp)
    failures = []
    try:
        run.measure_drift("before", seconds=10)
        for batch, phase in enumerate(["Init", "HL", "IU1", "IU2"]):
            with run.step(phase, batch, "status message") as st:
                ch.query(f"INSERT INTO DImessages VALUES (now64(3), {batch}, 'Orchestrator', 'Batch started', 'Status', NULL)",
                         query_id=st.query_id())
            if batch:
                with run.step(phase, batch, "load t", "t") as st:
                    ch.query(f"INSERT INTO t SELECT number FROM numbers({batch * 1_000_000})", query_id=st.query_id())
                    ch.query("SELECT sleepEachRow(0.5) FROM numbers(3) FORMAT Null", query_id=st.query_id())
                    time.sleep(0.5)                       # a gap between steps, counted in the phase
            with run.step(phase, batch, "validation.sql (PCR)", "DImessages", pcr=True) as st:
                ch.query("INSERT INTO DImessages SELECT now64(3), max(BatchID), 'Phase Complete Record', 'Batch Complete', "
                         "'PCR', NULL FROM DImessages", query_id=st.query_id())
        try:
            with run.step("IU2", 3, "failing step") as st:
                ch.query("SELECT throwIf(1, 'expected failure')", query_id=st.query_id())
        except RuntimeError:
            pass
        run.measure_drift("after", seconds=10)
        summary = run.finish()
        steps = list(csv.DictReader((run.dir / "steps.csv").open()))

        def check(name, ok, detail=""):
            print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
            if not ok:
                failures.append(name)

        print("checks")
        check("drift factor measured", 0.9 < run.factor() < 1.2, f"{run.factor():.4f}")
        check("steps.csv has one row per step", len(steps) == 12, str(len(steps)))
        load = [s for s in steps if s["step"] == "load t"]
        check("query_log stats matched on query_id", [int(s["written_rows"]) for s in load] == [1_000_000, 2_000_000, 3_000_000],
              str([s["written_rows"] for s in load]))
        check("durations corrected by the drift factor",
              all(abs(float(s["elapsed_s"]) * run.factor() - float(s["elapsed_raw_s"])) < 0.01 for s in steps))
        check("failed step recorded", steps[-1]["status"] == "error" and "expected failure" in steps[-1]["error"])
        check("CT0-CT3, EH, EI1, EI2", all(k in summary for k in ("CT0", "CT3", "EH", "EI1", "EI2")),
              f"EH {summary.get('EH')} EI1 {summary.get('EI1')} EI2 {summary.get('EI2')}")
        check("one PCR per batch", summary["pcr_problems"] == [])
        check("gap check: steps + gaps = phase times", len(summary["gap_check"]) == 3 and all(c["ok"] for c in summary["gap_check"]),
              str([(c["phase"], c["official_s"], c["steps_and_gaps_s"]) for c in summary["gap_check"]]))
        check("metric from digen_report.txt", "TPC_DI_RPS" in summary, str(summary.get("TPC_DI_RPS")))
        check("output files", all((run.dir / f).is_file() for f in
                                  ("steps.csv", "summary.json", "environment.json", "dimessages.csv")))
    finally:
        ClickHouse().query(f"DROP DATABASE IF EXISTS {db} SYNC")
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise SystemExit(f"{len(failures)} check(s) failed")
    print("SUCCESS: timing self-test")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="fake run on a throwaway database")
    parser.add_argument("--drift", type=float, metavar="SECONDS", help="only measure the drift factor")
    args = parser.parse_args()
    if args.drift:
        print(json.dumps(measure_drift(args.drift), indent=2))
    elif args.self_test:
        self_test()
    else:
        parser.print_help()
