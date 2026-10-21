#!/bin/sh
# Rebuilds classes/ from src/ (javac 21) against the API stand-ins in stubs/
# and ../blockcode/stubs (signatures only, no Minecraft code). Only the
# example mod's own classes are kept: every net/minecraft class must read as
# vanilla, which it does by its absence.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs ../blockcode/stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/render classes/com/example/
rm -rf build
