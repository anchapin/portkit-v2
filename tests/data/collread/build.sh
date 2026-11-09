#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the API stand-ins in
# ../blockcode/stubs (javac 21). Only the mod's classes are kept (#296: a
# block's collision read from a copied vanilla block's Properties, from a
# getCollisionShape box of its own, or settled when it is registered twice).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs src -name '*.java')
cp -r build/com/example/cmod classes/com/example/
rm -rf build
