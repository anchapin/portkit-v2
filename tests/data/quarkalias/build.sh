#!/bin/sh
# Rebuilds classes/ from src/ against stubs/ (javac 21): the shape of Quark
# 4.1's QuarkRemapHandler and its subscription (#296). Only src/'s classes
# are kept.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes/org/violetmoon/quark
javac --release 21 -g:none -d build $(find stubs src -name '*.java')
cp -r build/org/violetmoon/quark/base classes/org/violetmoon/quark/
rm -rf build
