#!/bin/sh
# Rebuilds classes/ from src/ (javac 21): stand-ins for the vanilla classes
# portkit.data.vanilla_blocks.derive reads out of a client jar. The test
# zips them into a jar with client.txt naming them as themselves.
set -e
cd "$(dirname "$0")"
rm -rf classes && mkdir -p classes
javac --release 21 -g:none -d classes $(find src -name '*.java')
