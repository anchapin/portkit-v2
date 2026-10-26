#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the API stand-ins in
# ../blockcode/stubs (javac 21). Only the mod's classes are kept (#296: a
# crop whose top half only grows, on vanilla CropBlock).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs src -name '*.java')
cp -r build/com/example/crop classes/com/example/
rm -rf build
