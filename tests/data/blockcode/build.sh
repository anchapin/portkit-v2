#!/bin/sh
# Rebuilds classes/ from src/ against the API stand-ins in stubs/ (javac 21).
# Only the example mod's own classes are kept: the converter must treat every
# net/minecraft class as vanilla, which it does by their absence. stubs/ are
# signatures only (no Minecraft code) so javac can resolve the calls.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/deco classes/com/example/
rm -f classes/com/example/deco/External.class
rm -rf build
