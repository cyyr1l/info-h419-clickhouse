# Builds the official TPC-DS tools (dsdgen + dsqgen) from the TPC zip, plus our
# rowcounts helper (expected row count of each table, used by gen_data.py).
#
# Build context: the unzipped kit, tools/DSGen-software-code-4.0.0, and the extra
# context "helper" = docker/tpcds-kit (see the tpcds-kit service in docker-compose.yml).
#
# Notes on the build:
# - flex and yacc are needed to build dsqgen (query grammar).
# - -fcommon is needed with GCC >= 10, otherwise the link fails with
#   "multiple definition of ..." errors (old C code relying on common symbols).
# - rowcounts reuses the dsdgen objects; driver.c is recompiled with -Dmain=dsdgen_main
#   so that rowcounts.c can provide its own main().

FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make flex bison byacc libc6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/tpcds
COPY . /opt/tpcds
COPY --from=helper rowcounts.c /opt/tpcds/tools/rowcounts.c

ARG CFLAGS_KIT="-D_FILE_OFFSET_BITS=64 -D_LARGEFILE_SOURCE -DYYDEBUG -DLINUX -g -Wall -fcommon"

RUN cd tools \
 && make -f Makefile.suite clean \
 && rm -f tokenizer.c y.tab.c y.tab.h \
 && make -f Makefile.suite OS=LINUX LINUX_CFLAGS="-g -Wall -fcommon" \
 && gcc $CFLAGS_KIT -Dmain=dsdgen_main -c driver.c -o driver_lib.o \
 && gcc $CFLAGS_KIT -o rowcounts rowcounts.c driver_lib.o \
        $(make -f Makefile.suite OS=LINUX --eval 'print-obj: ; @echo $(OBJ1)' print-obj \
          | tr ' ' '\n' | grep -v '^driver.o$') -lm \
 && test -x dsdgen && test -x dsqgen && test -x rowcounts

# dsdgen needs tpcds.idx from its working directory.
WORKDIR /opt/tpcds/tools
ENV PATH="/opt/tpcds/tools:${PATH}"

CMD ["dsdgen", "-HELP"]
