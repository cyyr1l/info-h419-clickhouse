#!/usr/bin/env python3
"""Generate the 9 TPC-DS queries whose reference result is empty at SF 1 with the official
qualification parameters (spec 4.0.0, Appendix B), so that they return rows and can be checked
against the kit's answer_sets/.

With our parameters (default seed), 10 reference results are empty at SF 1 (q08, q23_2, q24_1,
q24_2, q25, q29, q37, q41, q54, q58): a weak check. In kit 4.0.0, dsqgen -QUALIFY Y does not apply
the qualification values, so this script writes them into copies of the templates (every [PARAM]
outside the define lines) and runs dsqgen on those copies, in Docker, like gen_queries.py.

  python3 part1-tpcds/scripts/gen_qualify.py

writes
  part1-tpcds/queries/qualify/qNN.sql   netezza dialect, kit templates: source of reference/sf1_qualify
  data/queries/qualify/qNN.sql          clickhouse dialect + queries/templates/ + INTERVAL rewrite:
                                        the queries to run on ClickHouse
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_queries import KIT, OVERLAY, REPO, START, rewrite, run_in_kit  # noqa: E402

ZIPS = """
    24128 76232 65084 87816 83926 77556 20548 26231 43848 15126
    91137 61265 98294 25782 17920 18426 98235 40081 84093 28577
    55565 17183 54601 67897 22752 86284 18376 38607 45200 21756
    29741 96765 23932 89360 29839 25989 28898 91068 72550 10390
    18845 47770 82636 41367 76638 86198 81312 37126 39192 88424
    72175 81426 53672 10445 42666 66864 66708 41248 48583 82276
    18842 78890 49448 14089 38122 34425 79077 19849 43285 39861
    66162 77610 13695 99543 83444 83041 12305 57665 68341 25003
    57834 62878 49130 81096 18840 27700 23470 50412 21195 16021
    76107 71954 68309 18119 98359 64544 10336 86379 27068 39736
    98569 28915 24206 56529 57647 54917 42961 91110 63981 14922
    36420 23006 67467 32754 30903 20260 31671 51798 72325 85816
    68621 13955 36446 41766 68806 16725 15146 22744 35850 88086
    51649 18270 52867 39972 96976 63792 11376 94898 13595 10516
    90225 58943 39371 94945 28587 96576 57855 28488 26105 83933
    25858 34322 44438 73171 30122 34102 22685 71256 78451 54364
    13354 45375 40558 56458 28286 45266 47305 69399 83921 26233
    11101 15371 69913 35942 15882 25631 24610 44165 99076 33786
    70738 26653 14328 72305 62496 22152 10144 64147 48425 14663
    21076 18799 30450 63089 81019 68893 24996 51200 51211 45692
    92712 70466 79994 22437 25280 38935 71791 73134 56571 14060
    19505 72425 56575 74351 68786 51650 20004 18383 76614 11634
    18906 15765 41368 73241 76698 78567 97189 28545 76231 75691
    22246 51061 90578 56691 68014 51103 94167 57047 14867 73520
    15734 63435 25733 35474 24676 94627 53535 17879 15559 53268
    59166 11928 59402 33282 45721 43933 68101 33515 36634 71286
    19736 58058 55253 67473 41918 19515 36495 19430 22351 77191
    91393 49156 50298 87501 18652 53179 18767 63193 23968 65164
    68880 21286 72823 58470 67301 13394 31016 70372 67030 40604
    24317 45748 39127 26065 77721 31029 31880 60576 24671 45549
    13376 50016 33123 19769 22927 97789 46081 72151 15723 46136
    51949 68100 96888 64528 14171 79777 28709 11489 25103 32213
    78668 22245 15798 27156 37930 62971 21337 51622 67853 10567
    38415 15455 58263 42029 60279 37125 56240 88190 50308 26859
    64457 89091 82136 62377 36233 63837 58078 17043 30010 60099
    28810 98025 29178 87343 73273 30469 64034 39516 86057 21309
    90257 67875 40162 11356 73650 61810 72013 30431 22461 19512
    13375 55307 30625 83849 68908 26689 96451 38193 46820 88885
    84935 69035 83144 47537 56616 94983 48033 69952 25486 61547
    27385 61860 58048 56910 16807 17871 35258 31387 35458 35576
""".split()

# Official qualification substitution parameters, spec 4.0.0, Appendix B.
# A list is indexed from 1, as in the templates ([COLOR.1], [ZIP.400]).
PARAMS = {
    8:  {"YEAR": 1998, "QOY": 2, "ZIP": ZIPS},
    23: {"YEAR": 2000, "MONTH": 2, "TOPPERCENT": 50},
    24: {"MARKET": 8, "COLOR": ["peach", "saddle"], "AMOUNTONE": "ss_net_paid"},
    25: {"YEAR": 2001, "AGG": "sum"},
    29: {"YEAR": 1999, "MONTH": 9, "AGG": "sum"},
    37: {"PRICE": 68, "MANUFACT_ID": [677, 940, 694, 808], "INVDATE": "2000-02-01"},
    41: {"MANUFACT": 738,
         "SIZE": ["medium", "extra large", "N/A", "small", "petite", "large"],
         "UNIT": ["Ounce", "Oz", "Bunch", "Ton", "N/A", "Dozen", "Box", "Pound", "Pallet", "Gross",
                  "Cup", "Dram", "Each", "Tbl", "Lb", "Bundle"],
         "COLOR": ["powder", "khaki", "brown", "honeydew", "floral", "deep", "light", "cornflower",
                   "midnight", "snow", "cyan", "papaya", "orange", "frosted", "forest", "ghost"]},
    54: {"YEAR": 1998, "MONTH": 12, "CATEGORY": "Women", "CLASS": "maternity"},
    58: {"SALES_DATE": "2000-01-03"},
}
TOKEN = re.compile(r"\[([A-Z_]+)(?:\.(\d+))?\]")

PER_TEMPLATE = """
for i in {templates}; do
  rm -rf /qgen/tmp && mkdir /qgen/tmp
  dsqgen -DIRECTORY /qgen/templates -TEMPLATE query$i.tpl -DIALECT {dialect} -SCALE 1 \\
         -OUTPUT_DIR /qgen/tmp > /dev/null 2>&1 || true
  [ -s /qgen/tmp/query_0.sql ] || {{ echo "dsqgen produced nothing for query$i.tpl"; exit 1; }}
  cp /qgen/tmp/query_0.sql /qgen/out/q$(printf %02d $i).sql
done
rm -rf /qgen/tmp
"""


def qualify(text, params):
    """Replace every [PARAM] / [PARAM.n] outside the define lines by its qualification value."""
    used = set()

    def sub(m):
        name, idx = m.group(1), m.group(2)
        if name not in params:
            return m.group(0)                  # [_LIMITA], ... are left to dsqgen
        v = params[name]
        used.add(name)
        if isinstance(v, list):
            if idx is None:
                sys.exit(f"[{name}] needs an index")
            return str(v[int(idx) - 1])
        return str(v)

    out = "\n".join(l if l.lstrip().lower().startswith("define") else TOKEN.sub(sub, l)
                    for l in text.split("\n"))
    missing = set(params) - used
    if missing:
        sys.exit(f"parameters not found in the template: {sorted(missing)}")
    return out


def generate(dialect, overlay, out):
    work = Path(tempfile.mkdtemp(prefix="qgen-"))
    try:
        shutil.copytree(KIT, work / "templates")
        for f in overlay:
            shutil.copy(f, work / "templates" / f.name)
        if dialect == "netezza":   # kit 4.0.0: netezza.tpl lacks the _END define dsqgen needs
            netezza = work / "templates" / "netezza.tpl"
            if "_END" not in netezza.read_text():
                with netezza.open("a") as f:
                    f.write('define _END = "";\n')
        for q, params in PARAMS.items():
            tpl = work / "templates" / f"query{q}.tpl"
            tpl.write_text(qualify(tpl.read_text(), params))
        (work / "out").mkdir()
        for d in (work, work / "out"):
            os.chmod(d, 0o777)   # the container runs as another user id on some machines
        run_in_kit(work, PER_TEMPLATE.format(dialect=dialect, templates=" ".join(map(str, PARAMS))))

        files = sorted((work / "out").glob("*.sql"))
        if len(files) != len(PARAMS):
            sys.exit(f"dsqgen wrote {len(files)} files instead of {len(PARAMS)}")
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            text = f.read_text(encoding="utf-8")
            if dialect == "clickhouse":
                text = rewrite(text)
                if len(START.findall(text)) != 1:
                    sys.exit(f"{f.name}: expected 1 query marker")
            if TOKEN.search(text):
                sys.exit(f"{f.name}: unsubstituted parameter left")
            (out / f.name).write_text(text, encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"{len(files)} files in {out}")


def main():
    if not (KIT / "templates.lst").exists():
        sys.exit(f"TPC-DS kit not found: unzip it into {KIT.parent.parent} (see the README)")
    generate("netezza", [], REPO / "part1-tpcds" / "queries" / "qualify")
    generate("clickhouse", sorted(OVERLAY.glob("*.tpl")), REPO / "data" / "queries" / "qualify")


if __name__ == "__main__":
    main()
