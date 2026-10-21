#!/bin/sh
# Rebuilds classes/ (an example mod registering its own recipe serializers,
# #358) from src/ against stubs/ (javac 21).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
cp -r build/com/example/rmod classes/com/example/
rm -rf build
