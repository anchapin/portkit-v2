#!/bin/sh
# Rebuilds classes/ (an AE2-like mod) from src/ against the API stand-ins in
# ../blockcode/stubs (javac 21). Only the mod's classes are kept (#296: facing
# and spin placed by AE2's FacingWithSpinStrategy, read by the ae2 adapter).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find ../blockcode/stubs src -name '*.java')
cp -r build/appeng classes/
rm -rf build
