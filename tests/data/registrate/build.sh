#!/bin/sh
# Rebuilds classes/ from src/ (javac 21) against the API stand-ins in stubs/
# (Registrate's builder, signatures only) and ../rendershape/stubs,
# ../blockcode/stubs (no Minecraft code). Only the example mod's own classes
# are kept: Registrate and net/minecraft read by their absence, as a library
# and as vanilla.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs ../rendershape/stubs ../blockcode/stubs src -name '*.java')
mkdir -p classes/com/example && cp -r build/com/example/regi classes/com/example/
rm -rf build
