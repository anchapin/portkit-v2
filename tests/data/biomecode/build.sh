#!/bin/sh
# Rebuilds classes/ from src/ against the API stand-ins in stubs/ (javac 21).
# Only the example mod's own classes are kept: Minecraft and Fabric API classes
# are absent, as in a real mod jar. stubs/ are signatures only (no Minecraft or
# Fabric code) so javac can resolve the calls; their names are the Mojang ones
# (a real Fabric jar is read through its intermediary mapping, #235) and Fabric
# API's (net.fabricmc.fabric.api.biome.v1, Fabric API 0.116.17+1.21.1).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/ores classes/com/example/
rm -rf build
