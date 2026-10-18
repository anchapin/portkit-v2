#!/bin/sh
# Rebuilds classes/ (the example mod) and library/ (the example library) from
# src/ and lib/ against the API stand-ins in ../blockcode/stubs and stubs/
# here (javac 21). Minecraft classes are dropped: the converter treats every
# net/minecraft class as vanilla by its absence.
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes library
javac --release 21 -g:none -d build $(find ../blockcode/stubs stubs lib src -name '*.java')
mkdir -p classes/com/example library/com/example
cp -r build/com/example/imod classes/com/example/
cp -r build/com/example/ilib library/com/example/
rm -rf build
