#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the example library
# and stubs of ../inheritcode and the API stand-ins in ../blockcode/stubs
# (javac 21). Only the mod's classes are kept; tests read it with
# ../inheritcode/library.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs ../inheritcode/stubs ../inheritcode/lib src -name '*.java')
cp -r build/com/example/vmod classes/com/example/
rm -rf build
