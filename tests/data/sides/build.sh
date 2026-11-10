#!/bin/sh
# Rebuilds classes/ (the example mod) and lib/classes (its dependency jar) from
# src/ and lib/ against the stand-ins in stubs/, ../lazycode/stubs and
# ../blockcode/stubs (javac 21). The stand-ins' code isn't kept, as when a mod
# is read with its dependency jar but without Fabric Loader or Minecraft (#296).
set -e
cd "$(dirname "$0")"
rm -rf classes libclasses build && mkdir -p build classes/com/example libclasses/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs ../lazycode/stubs stubs lib src -name '*.java')
cp -r build/com/example/smod classes/com/example/
cp -r build/com/example/slib libclasses/com/example/
rm -rf build
