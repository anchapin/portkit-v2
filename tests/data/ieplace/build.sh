#!/bin/sh
# Rebuilds classes/ (Immersive Engineering's placement chain cut down) from src/
# against the API stand-ins in ../blockcode/stubs (javac 21). Only the mod's
# classes are kept (#296: facing set by the block entity after placement, read
# by the immersiveengineering adapter).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find ../blockcode/stubs src -name '*.java')
cp -r build/blusunrize classes/
rm -rf build
