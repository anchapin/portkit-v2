#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ and library/ (the example
# library, read-only, #280) from lib/ against ../inheritcode's example library
# and stubs and ../blockcode/stubs (javac 21). Zeta's VariantRegistry shape: a
# final per-object LinkedHashMap filled through an object a library event
# hands over, and read in another module's run (Quark's vertical slabs).
set -e
cd "$(dirname "$0")"
rm -rf classes library build && mkdir -p build classes/com/example library/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs ../inheritcode/stubs ../inheritcode/lib lib src -name '*.java')
cp -r build/com/example/vmod classes/com/example/
cp -r build/com/example/ilib build/com/example/vlib library/com/example/
rm -rf build
