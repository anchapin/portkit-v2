#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the stand-ins in
# stubs/, ../lazycode/stubs and ../blockcode/stubs (javac 21). The stand-ins'
# code isn't kept, as when a mod is read without Forge, NeoForge or Minecraft
# (#296).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs ../lazycode/stubs stubs src -name '*.java')
cp -r build/com/example/fmod classes/com/example/
rm -rf build
