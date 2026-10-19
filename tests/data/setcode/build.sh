#!/bin/sh
# Rebuilds classes/ (the example mod) and library/ (the example library jar's
# classes) from src/ and lib/ against the API stand-ins in ../blockcode/stubs
# plus those in stubs/ here (javac 21). Minecraft classes are dropped: the
# converter treats every net/minecraft class as vanilla by its absence.
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes library
stubs=$(find ../blockcode/stubs -name '*.java' | grep -v 'state/properties/BlockSetType.java')
javac --release 21 -g:none -d build $stubs $(find stubs lib src -name '*.java')
mkdir -p classes/com/example library/com/example
cp -r build/com/example/setmod classes/com/example/
cp -r build/com/example/setlib library/com/example/
rm -rf build
