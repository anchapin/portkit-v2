#!/bin/sh
# javac 21 output of src (plain Java, no Minecraft classes); rebuild with: sh build.sh
cd "$(dirname "$0")" && rm -rf classes && mkdir classes && javac --release 21 -d classes $(find src -name '*.java')
