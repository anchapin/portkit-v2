#!/bin/sh
# Rebuilds classes/ (the example mod), library/ (its library, read-only) and
# reflect/ (one class that instantiates by reflection) from src/, lib/ and
# reflectsrc/ against stubs/ and ../blockcode/stubs (javac 21, #280 loader
# entry classes).
set -e
cd "$(dirname "$0")"
rm -rf classes library reflect build && mkdir -p build classes/com/example library/com/example reflect/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs stubs lib src reflectsrc -name '*.java')
cp -r build/com/example/emod classes/com/example/
cp -r build/com/example/elib library/com/example/
cp -r build/com/example/eref reflect/com/example/
rm -rf build
