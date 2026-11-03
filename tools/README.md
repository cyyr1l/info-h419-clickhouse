# THE TPC SOFTWARE IS AVAILABLE WITHOUT CHARGE FROM TPC.

`DSGen-software-code-4.0.0/` is the TPC-DS kit, version 4.0.0, from the Transaction Processing
Performance Council (https://www.tpc.org). It is redistributed here unmodified, under clause 9 of the
TPC End User License Agreement, whose complete text is in
[`DSGen-software-code-4.0.0/EULA.txt`](DSGen-software-code-4.0.0/EULA.txt). The specification document
(`specification/specification_4.0.0.pdf`) is left out; it is available on the TPC website.

The kit is included so that the benchmark can be rerun right after cloning the repository. Our scripts
build `dsdgen` and `dsqgen` from this folder in a Docker image (`docker/tpcds-kit/Dockerfile`). Our
changes to the query templates are in `part1-tpcds/queries/templates/`, not in this folder.

Results produced with this kit in this repository are derived from TPC-DS and are not comparable to
published TPC Benchmark Results.
