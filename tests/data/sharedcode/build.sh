#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against ../inheritcode's
# example library (lib/, Zeta's shapes) and stubs and ../blockcode/stubs
# (javac 21). library/ holds the library's classes, read-only (#280).
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes/com/example library/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs ../inheritcode/stubs ../inheritcode/lib src -name '*.java')
cp -r build/com/example/smod classes/com/example/
cp -r build/com/example/ilib library/com/example/
rm -rf build
