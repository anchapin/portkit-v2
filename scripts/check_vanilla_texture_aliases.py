"""Re-run the pixel check behind ``portkit.data.vanilla_texture_aliases`` (#296).

The table pairs a Java vanilla texture name with the Bedrock file its Bedrock
short name of the same name shows, when that file is filed under another name
(``oak_planks`` -> ``textures/blocks/planks_oak``). A pair is kept only when
the Bedrock file looks exactly like the Java texture. This script is the
method, so the table can be checked or re-derived; nothing it reads is kept.

Inputs (both downloaded to a scratch directory, never committed):

- the Java client jar, ``--jar PATH``; its sha1 must be
  ``vanilla_texture_aliases.JAVA_CLIENT_SHA1`` (Minecraft 1.21.11, from
  Mojang's launcher manifest piston-meta.mojang.com);
- the Bedrock texture files the candidates point at, from Mojang/bedrock-samples
  at the commit pinned in ``portkit.data`` (``resource_pack/<file>.png``, else
  ``.tga``).

Candidates come from the cached vanilla atlas index (``portkit reference
fetch``): every short name in ``terrain_texture.json`` / ``item_texture.json``
that shows exactly one file, where Bedrock has no file of that name (top level
or one folder down) and the Java jar has ``textures/block/<name>.png``
(``item/`` for the item atlas).

The check (needs Pillow): both images decoded to RGBA; same width and height; every pixel has
the same alpha, and every pixel with alpha > 0 has the same colour. Colours
under fully transparent pixels are ignored (they never show). Anything else,
a size difference included, is "differs" and stays residue.

    python scripts/check_vanilla_texture_aliases.py --jar client.jar           # print the tables
    python scripts/check_vanilla_texture_aliases.py --jar client.jar --check   # exit 1 if stale
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from portkit import data  # noqa: E402
from portkit.data import vanilla_texture_aliases as aliases  # noqa: E402
from portkit.data import vanilla_textures  # noqa: E402

LANES = {"terrain": ("textures/blocks/", "block"), "item": ("textures/items/", "item")}


def decode(raw: bytes) -> tuple[int, int, bytes] | None:
    """(width, height, RGBA) through Pillow, which reads every PNG form
    (interlaced, grey with tRNS) and Bedrock's TGAs alike."""
    try:
        from PIL import Image
    except ImportError:  # maintenance-only dependency
        raise SystemExit("this check needs Pillow (pip install pillow)")
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
    except OSError:
        return None
    return image.width, image.height, image.tobytes()


def same_look(a: tuple[int, int, bytes], b: tuple[int, int, bytes]) -> bool:
    if a[:2] != b[:2]:
        return False
    pa, pb = a[2], b[2]
    for i in range(0, len(pa), 4):
        if pa[i + 3] != pb[i + 3]:
            return False
        if pa[i + 3] and pa[i: i + 3] != pb[i: i + 3]:
            return False
    return True


def candidates(index, java_names) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for home, (folder, java_lane) in LANES.items():
        found = {}
        for short, entry in index.atlases[home].items():
            if folder + short in index.files[home] or index.nested(home, folder, short):
                continue
            if len(entry["paths"]) != 1 or f"{java_lane}/{short}" not in java_names:
                continue
            found[short] = entry["paths"][0]
        out[home] = dict(sorted(found.items()))
    return out


def bedrock_image(file: str, scratch: Path) -> tuple[int, int, bytes] | None:
    for ext in (".png", ".tga"):
        local = scratch / (file.replace("/", "__") + ext)
        if not local.exists():
            url = f"https://raw.githubusercontent.com/{data.REPO}/{data.COMMIT}/resource_pack/{file}{ext}"
            try:
                request = urllib.request.Request(url, headers={"User-Agent": data._USER_AGENT})
                with urllib.request.urlopen(request, timeout=60) as response:
                    local.write_bytes(response.read())
            except OSError:
                continue
        return decode(local.read_bytes())
    return None


def derive(jar: Path, scratch: Path) -> tuple[dict, dict]:
    index = vanilla_textures.index()
    if index is None:
        raise SystemExit(f"vanilla texture index not cached; run `{data.FETCH_COMMAND}`")
    with zipfile.ZipFile(jar) as z:
        prefix = "assets/minecraft/textures/"
        java_names = {n[len(prefix):-4] for n in z.namelist() if n.startswith(prefix) and n.endswith(".png")}
        same: dict[str, dict[str, str]] = {}
        differs: dict[str, dict[str, str]] = {}
        for home, pairs in candidates(index, java_names).items():
            java_lane = LANES[home][1]
            same[home], differs[home] = {}, {}
            for name, file in pairs.items():
                java = decode(z.read(f"{prefix}{java_lane}/{name}.png"))
                bedrock = bedrock_image(file, scratch)
                ok = java is not None and bedrock is not None and same_look(java, bedrock)
                (same if ok else differs)[home][name] = file
    return same, differs


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", required=True, type=Path, help="Minecraft 1.21.11 client jar")
    parser.add_argument("--check", action="store_true", help="exit 1 if the pinned tables differ")
    args = parser.parse_args(argv)
    sha1 = hashlib.sha1(args.jar.read_bytes()).hexdigest()
    if sha1 != aliases.JAVA_CLIENT_SHA1:
        print(f"jar sha1 {sha1} is not the pinned {aliases.JAVA_CLIENT_SHA1}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as scratch:
        same, differs = derive(args.jar, Path(scratch))
    if args.check:
        stale = same != aliases.ALIASES or differs != aliases.DIFFERS
        counts = {home: (len(same[home]), len(differs[home])) for home in same}
        if stale:
            print(f"tables are stale: derived (same, differs) {counts}", file=sys.stderr)
            return 1
        print(f"tables are current (same, differs) {counts}")
        return 0
    print(json.dumps({"ALIASES": same, "DIFFERS": differs}, indent=4, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
