#!/bin/sh
# Rebuilds classes/ from src/ against the API stand-ins in stubs/ (javac 21).
# Only the example mod's own classes are kept: Minecraft and Forge classes are
# absent, as in a real mod jar. stubs/ are signatures only (no Minecraft or
# Forge code) so javac can resolve the calls; their method names are the
# Mojang ones (EntityType.Builder.of/sized).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/mobs classes/com/example/
rm -rf build
