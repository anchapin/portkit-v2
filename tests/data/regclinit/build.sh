#!/bin/sh
# Rebuilds classes/ (the example mod) from src/ against the stand-in library
# in stubs/ and the API stand-ins in ../blockcode/stubs (javac 21). Only the
# mod's classes are kept: the library's code isn't there, as when a mod is
# read without its dependency jars (#296: a registry class initializer that
# calls a helper the reading can't finish).
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/com/example
javac --release 21 -g:none -d build $(find ../blockcode/stubs stubs src -name '*.java')
cp -r build/com/example/cmod classes/com/example/
rm -rf build
