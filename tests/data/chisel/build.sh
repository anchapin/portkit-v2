#!/bin/sh
# Rebuilds classes/ from src/ against the stand-ins in stubs/ (javac 21).
# src/ mirrors the shape of Chisel 1.12/dev's own classes (team/chisel/**,
# all in the Chisel jar): Features' builder chains and the builder API they
# call. stubs/ are signatures of the Minecraft 1.12 classes they name, left
# out of classes/ so the reader treats them as vanilla.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
cp -r build/team classes/
rm -rf build
