#!/bin/sh
# Rebuilds classes/ from src/ (javac 17+). The stand-in stats API under
# src/slimeknights mirrors the Tinkers names the reader looks for; stubs/ holds
# a signature-only ResourceLocation, kept out of classes/ like any vanilla class.
set -e
cd "$(dirname "$0")"
rm -rf classes build && mkdir -p build classes
javac --release 17 -g:none -d build $(find stubs src -name '*.java')
cp -r build/com build/slimeknights classes/
rm -rf build
