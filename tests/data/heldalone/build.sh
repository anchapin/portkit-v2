#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the API stand-ins in
# ../blockcode/stubs (javac 21). Only the mod's classes are kept (#296: an
# enum state alone, held at its start).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs src -name '*.java')
cp -r build/com/example/lone classes/com/example/
rm -rf build
