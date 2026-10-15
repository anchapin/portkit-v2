#!/bin/sh
# Rebuilds classes/ from src/ against the API stand-ins in stubs/ (javac 21).
# Only the example mod's own classes are kept: Citadel's GuiBasicBook and every
# net/minecraft class must be absent, as they are from a real mod's jar.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/books classes/com/example/
rm -rf build
