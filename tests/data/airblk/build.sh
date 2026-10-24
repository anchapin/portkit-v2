#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the API stand-ins in
# ../blockcode/stubs (javac 21). Only the mod's classes are kept (#296: a
# block registered as air, Properties#air).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs src -name '*.java')
cp -r build/com/example/amod classes/com/example/
rm -rf build
