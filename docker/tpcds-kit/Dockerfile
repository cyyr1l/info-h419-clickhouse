# Builds the official TPC-DS tools (dsdgen + dsqgen) from the TPC zip.
#
# Build context: the unzipped kit, tools/DSGen-software-code-4.0.0
# (see the tpcds-kit service in docker/docker-compose.yml).
#
# Notes on the build:
# - flex and yacc are needed to build dsqgen (query grammar).
# - -fcommon is needed with GCC >= 10, otherwise the link fails with
#   "multiple definition of ..." errors (old C code relying on common symbols).

FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make flex bison byacc libc6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/tpcds
COPY . /opt/tpcds

RUN cd tools \
 && make -f Makefile.suite clean \
 && rm -f tokenizer.c y.tab.c y.tab.h \
 && make -f Makefile.suite OS=LINUX LINUX_CFLAGS="-g -Wall -fcommon" \
 && test -x dsdgen && test -x dsqgen

# dsdgen needs tpcds.idx from its working directory.
WORKDIR /opt/tpcds/tools
ENV PATH="/opt/tpcds/tools:${PATH}"

CMD ["dsdgen", "-HELP"]
