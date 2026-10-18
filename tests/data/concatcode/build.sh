#!/bin/sh
# Rebuilds classes/ (the example mod) and library/ (the example library's
# classes) from src/ and lib/ plus ../libcode/lib against the API stand-ins in
# ../blockcode/stubs, ../libcode/stubs and stubs/ here (javac 21). Minecraft
# classes are dropped: the converter treats every net/minecraft class as
# vanilla by its absence.
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes library
stubs=$(find ../blockcode/stubs -name '*.java' | grep -v 'state/properties/BlockSetType.java')
javac --release 21 -g:none -d build $stubs $(find ../libcode/stubs ../libcode/lib stubs lib src -name '*.java')
mkdir -p classes/com/example library/com/example
cp -r build/com/example/concat classes/com/example/
cp -r build/com/example/lib library/com/example/
rm -rf build
