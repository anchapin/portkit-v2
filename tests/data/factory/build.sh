#!/bin/sh
# Rebuilds classes/ (the example mod) and library/ (the example library jar's
# classes) from src/ and lib/ against the API stand-ins in ../blockcode/stubs
# (javac 21). #296: a library builder calls the factory the mod registered
# with a copy of a vanilla block's Properties.
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes/com/example library/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs lib src -name '*.java')
cp -r build/com/example/fmod classes/com/example/
cp -r build/com/example/flib library/com/example/
rm -rf build
