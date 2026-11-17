# TPC-DI data generator (DIGen 1.1.0) on Java 8.
# Built from the DIGen zip downloaded from tpc.org into tools/ (not in Git: the PDGF licence
# does not allow redistribution). Built and run by part2-tpcdi/scripts/gen_data.py.
FROM eclipse-temurin:8-jre

RUN apt-get update \
 && apt-get install -y --no-install-recommends unzip \
 && rm -rf /var/lib/apt/lists/*

COPY *TPC-DI-Tool.zip /tmp/digen.zip

# DIGen.jar and its PDGF folder go to /opt/digen. DIGen looks for "pdgf" but the zip may
# contain "PDGF" (or the other way round): add the missing name as a symlink.
# PDGF writes into its own folder, and the container runs as the host user: make it writable.
RUN mkdir -p /tmp/x /opt/digen \
 && unzip -q /tmp/digen.zip -d /tmp/x \
 && jar_dir="$(dirname "$(find /tmp/x -name DIGen.jar | head -n 1)")" \
 && cp -a "$jar_dir"/. /opt/digen/ \
 && cd /opt/digen \
 && if [ -d PDGF ] && [ ! -e pdgf ]; then ln -s PDGF pdgf; fi \
 && if [ -d pdgf ] && [ ! -e PDGF ]; then ln -s pdgf PDGF; fi \
 && test -f DIGen.jar && test -e pdgf \
 && chmod -R a+rwX /opt/digen \
 && rm -rf /tmp/x /tmp/digen.zip

ENV HOME=/tmp
WORKDIR /opt/digen
