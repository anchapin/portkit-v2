"""TEMPORARY (#372, reverted before merge): print a sha256 over the output tree."""
import atexit
import hashlib
import os
import sys


def install(out):
    def report():
        h = hashlib.sha256()
        n = 0
        for root, dirs, files in os.walk(out):
            dirs.sort()
            for f in sorted(files):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, out)
                with open(p, "rb") as fh:
                    data = fh.read()
                h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
                n += 1
        print(f"[treehash372] {n} files sha256 {h.hexdigest()}", file=sys.stderr, flush=True)
    atexit.register(report)
