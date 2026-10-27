#!/bin/sh
# Rebuilds classes/ from src/ against the stand-ins in stubs/ (javac 21 at
# --release 8, the Java 8 bytecode Forge 1.12 mods ship). src/ is written for
# this test (not taken from any jar): blocks that answer Forge 1.12's
# Block#canRenderInLayer / Block#getBlockLayer in the shapes the reader
# accepts, and one it doesn't. stubs/ are signatures of the Minecraft 1.12
# classes they name, left out of classes/ so the reader treats them as vanilla.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 8 -g:none -nowarn -d build $(find stubs src -name '*.java')
cp -r build/com classes/
rm -rf build
