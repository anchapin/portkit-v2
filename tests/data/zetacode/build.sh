#!/bin/sh
# Rebuilds classes/ (the example Zeta mod) and library/ (stand-ins for the
# Zeta 1.1-40 classes the flag reader reads: org/violetmoon/zeta, the same
# names, elements and defaults) from src/ and lib/ (javac 21).
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes library
javac --release 21 -g:none -d build $(find lib src -name '*.java')
mkdir -p classes/com/example library/org
cp -r build/com/example/zmod classes/com/example/
cp -r build/org/violetmoon library/org/
rm -rf build
