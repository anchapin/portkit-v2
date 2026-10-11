"""Check or re-pin the Bedrock vanilla sound list (#116, #124).

The list is every audio path Bedrock's vanilla resource pack names in its
sound_definitions.json, read from Mojang/bedrock-samples at the commit pinned
in ``portkit.data`` (the same commit as the agent reference). It is Mojang's
data, so it is not committed: ``portkit reference fetch`` downloads and caches
it, and refuses a list whose sha256 differs from ``portkit.data.SOUNDS_SHA256``.
This script derives the list from upstream and reports that hash, so a commit
bump and its new hash land together.

    python scripts/build_vanilla_sounds.py           # print the sha256 to pin
    python scripts/build_vanilla_sounds.py --check   # exit 1 if the pin is stale
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from portkit import data  # noqa: E402


def main(argv: list[str]) -> int:
    with urllib.request.urlopen(data.URL, timeout=60) as resp:
        text = data.derive_sounds(resp.read())
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    count = sum(1 for line in text.splitlines() if line and not line.startswith("#"))
    if "--check" in argv:
        if digest != data.SOUNDS_SHA256:
            print(
                f"SOUNDS_SHA256 is stale: {data.URL} derives {digest}; "
                "set it in src/portkit/data/__init__.py",
                file=sys.stderr,
            )
            return 1
        print(f"SOUNDS_SHA256 is current ({count} paths)")
        return 0
    print(f"{digest}  ({count} paths from {data.REPO}@{data.COMMIT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
