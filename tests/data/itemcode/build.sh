#!/bin/sh
# Rebuilds classes/ from src/ against the API stand-ins in stubs/ (javac 21),
# as tests/data/blockcode/build.sh does: only the example mod's classes are
# kept, so every net/minecraft class is vanilla by its absence (#268).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/toy classes/com/example/
rm -rf build
