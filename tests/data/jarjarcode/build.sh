#!/bin/sh
# Rebuilds classes/ (the example mod) and library/ (the example bundled
# library's classes) from src/ and lib/ against the API stand-ins in
# ../blockcode/stubs (javac 21). Minecraft classes are dropped: the converter
# treats every net/minecraft class as vanilla by its absence (#368).
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes library
stubs=$(find ../blockcode/stubs -name '*.java')
javac --release 21 -g:none -d build $stubs $(find lib src -name '*.java')
mkdir -p classes/com/example library/com/example
cp -r build/com/example/jjmod classes/com/example/
cp -r build/com/example/jjlib library/com/example/
rm -rf build
