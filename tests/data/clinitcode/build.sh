#!/bin/sh
# Rebuilds classes/ from src/ (javac 21) against the API stand-ins in stubs/,
# ../blockcode/stubs and ../rendershape/stubs (signatures only, no Minecraft
# code). Only the example mod's own classes are kept: what the stubs stand
# for (com/example/clinitext: calls the run can't follow) is absent.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs ../blockcode/stubs ../rendershape/stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/clinit classes/com/example/
rm -rf build
