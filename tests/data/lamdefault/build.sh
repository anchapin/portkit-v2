#!/bin/sh
# Rebuilds classes/ (the example mod) and library/ (the example library jar's
# classes) from src/ and lib/ against the API stand-ins in ../blockcode/stubs
# (javac 21). hidden/ is compiled against and never copied: code outside the
# jar and its libraries. #296: a call on a lambda of its interface's default
# method (Registrate's NonNullFunction#andThen).
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes/com/example library/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs lib src hidden -name '*.java')
cp -r build/com/example/lmod classes/com/example/
cp -r build/com/example/llib library/com/example/
rm -rf build
