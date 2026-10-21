#!/bin/sh
# Rebuilds classes/ (the example mod's client code registering item
# properties, #344) from src/ against stubs/ (javac 21).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
cp -r build/com/example/pmod classes/com/example/
rm -rf build
