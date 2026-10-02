"""Settle the model axis convention with one look in game.

Java element boxes and Bedrock geometry cubes are both axis-aligned boxes in a
16-unit block, so the transform is arithmetic. Exactly one detail is not
written down anywhere we could verify: whether Bedrock's X axis runs the same
way as Java's. Both readings produce a model that loads and renders, and on a
symmetric shape both look identical, which is how a mirrored port ships.

So rather than guess, this builds a pack holding the SAME asymmetric Java model
converted both ways, side by side:

    examplemod:probe_direct    origin.x = from.x - 8      (axes agree)
    examplemod:probe_mirrored  origin.x = 8 - to.x        (X is flipped)

Place both, stand facing north (F3 in Java, or the sun rises east), and see
which one puts its slab on the same side as the Java original. That answer is
the constant the real converter needs, and it only has to be found once.
"""
from __future__ import annotations

import json
from pathlib import Path

CANDIDATES = ("direct", "mirrored")
SIGNS = ("aswritten", "negated")
AXES = ("x", "y", "z")

_GEOMETRY_FORMAT = "1.16.0"
_BLOCK_FORMAT = "1.20.10"


def _cube(element: dict, candidate: str) -> dict:
    """One Java element as a Bedrock cube, under one reading of the X axis."""
    x1, y1, z1 = (float(v) for v in element["from"])
    x2, y2, z2 = (float(v) for v in element["to"])

    origin_x = x1 - 8 if candidate == "direct" else 8 - x2
    cube = {
        "origin": [origin_x, y1, z1 - 8],
        "size": [x2 - x1, y2 - y1, z2 - z1],
    }

    uv: dict[str, dict] = {}
    for face, spec in (element.get("faces") or {}).items():
        box = spec.get("uv")
        if not (isinstance(box, list) and len(box) == 4):
            continue
        u1, v1, u2, v2 = (float(v) for v in box)
        uv[face] = {"uv": [u1, v1], "uv_size": [u2 - u1, v2 - v1]}
    if uv:
        cube["uv"] = uv
    return cube


def geometry(model: dict, identifier: str, candidate: str) -> dict:
    """A Bedrock geometry file for a Java model's elements."""
    elements = model.get("elements") or []
    return {
        "format_version": _GEOMETRY_FORMAT,
        "minecraft:geometry": [
            {
                "description": {
                    "identifier": identifier,
                    "texture_width": 16,
                    "texture_height": 16,
                    "visible_bounds_width": 2,
                    "visible_bounds_height": 2.5,
                    "visible_bounds_offset": [0, 0.75, 0],
                },
                "bones": [
                    {
                        "name": "root",
                        "pivot": [0, 0, 0],
                        "cubes": [_cube(e, candidate) for e in elements],
                    }
                ],
            }
        ],
    }


def block(namespace: str, name: str, identifier: str, texture: str) -> dict:
    return {
        "format_version": _BLOCK_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": "construction"},
            },
            "components": {
                "minecraft:geometry": identifier,
                "minecraft:material_instances": {
                    "*": {"texture": texture, "render_method": "opaque"}
                },
            },
        },
    }


def build(model_file: Path, namespace: str, texture: str) -> dict[str, object]:
    """The probe pack's files, keyed by their path inside the tree."""
    model = json.loads(model_file.read_text())
    if not model.get("elements"):
        raise ValueError(f"{model_file} has no elements to probe with")

    files: dict[str, object] = {}
    names = []
    for candidate in CANDIDATES:
        name = f"probe_{candidate}"
        identifier = f"geometry.{namespace}.{name}"
        files[f"models/blocks/{name}.geo.json"] = geometry(model, identifier, candidate)
        files[f"blocks/{name}.json"] = block(namespace, name, identifier, texture)
        names.append(name)

    files["texts/en_US.lang"] = "\n".join(
        [
            f"tile.{namespace}:probe_direct.name=Probe A (axes agree)",
            f"tile.{namespace}:probe_mirrored.name=Probe B (X flipped)",
            "",
        ]
    )
    return files


def pack_files(model_file: Path, texture_file: Path, namespace: str) -> dict[str, object]:
    """Everything the probe pack contains, ready for pack.write_tree."""
    texture_key = f"{namespace}:probe"
    files = build(model_file, namespace, texture_key)
    files["textures/blocks/probe.png"] = texture_file.read_bytes()
    files["textures/terrain_texture.json"] = {
        "resource_pack_name": namespace,
        "texture_name": "atlas.terrain",
        "texture_data": {texture_key: {"textures": "textures/blocks/probe"}},
    }
    return files


# ---------------------------------------------------------------- rotation --
#
# The X axis is settled (see converters/models.X_AXIS_IS_FLIPPED), and a mirror
# on X should negate a rotation about Y and about Z while leaving one about X
# alone. Should. That is a prediction from the mirror, not something anyone
# documented, and a wrong sign gives you a model that loads, renders, and leans
# the wrong way. So the same trick: both signs, side by side, one look.
#
# Pivot is deliberately not probed here. Every bar below turns about the block
# centre, where the pivot transform is the identity, so the only thing these
# blocks can disagree about is the sign. A Java rotation about any other origin
# stays refused until it gets a probe of its own.

_JAVA_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# What Java renders for each probe bar at +22.5, derived in
# docs/rotation-convention.md from vanilla's wall torch. It belongs to the axis,
# not to either candidate: both candidates for an axis carry the same line, and
# whichever block actually looks like it is the one that matches Java.
EXPECTED_LEAN = {
    "x": "north end up",
    "y": "east end swings north",
    "z": "east end up",
}


def rotated_cube(element: dict, sign: str) -> dict:
    """A Java rotated element as a Bedrock cube, under one reading of the sign."""
    cube = _cube(element, "mirrored")
    rotation = element.get("rotation") or {}
    angle = float(rotation.get("angle", 0))
    axis = str(rotation.get("axis", "y"))
    origin = [float(v) for v in rotation.get("origin", [8, 8, 8])]

    degrees = [0.0, 0.0, 0.0]
    degrees[_JAVA_AXIS_INDEX[axis]] = -angle if sign == "negated" else angle
    cube["pivot"] = [8 - origin[0], origin[1], origin[2] - 8]
    cube["rotation"] = degrees
    return cube


def rotation_pack_files(
    model_dir: Path, texture_file: Path, namespace: str
) -> dict[str, object]:
    """One block per axis per sign: six blocks, three questions, one look."""
    files: dict[str, object] = {}
    labels = []
    for axis in AXES:
        model_file = model_dir / f"rot_{axis}.json"
        model = json.loads(model_file.read_text())
        if not model.get("elements"):
            raise ValueError(f"{model_file} has no elements to probe with")
        for sign in SIGNS:
            name = f"rot_{axis}_{sign}"
            identifier = f"geometry.{namespace}.{name}"
            files[f"models/blocks/{name}.geo.json"] = {
                "format_version": _GEOMETRY_FORMAT,
                "minecraft:geometry": [
                    {
                        "description": {
                            "identifier": identifier,
                            "texture_width": 16,
                            "texture_height": 16,
                            "visible_bounds_width": 3,
                            "visible_bounds_height": 3,
                            "visible_bounds_offset": [0, 0.75, 0],
                        },
                        "bones": [
                            {
                                "name": "root",
                                "pivot": [0, 0, 0],
                                "cubes": [
                                    rotated_cube(e, sign) for e in model["elements"]
                                ],
                            }
                        ],
                    }
                ],
            }
            files[f"blocks/{name}.json"] = block(
                namespace, name, identifier, f"{namespace}:probe"
            )
            written = "as written" if sign == "aswritten" else "negated"
            labels.append(
                f"tile.{namespace}:{name}.name={axis.upper()} {written} "
                f"(Java: {EXPECTED_LEAN[axis]})"
            )

    files["texts/en_US.lang"] = "\n".join(labels + [""])
    files["textures/blocks/probe.png"] = texture_file.read_bytes()
    files["textures/terrain_texture.json"] = {
        "resource_pack_name": namespace,
        "texture_name": "atlas.terrain",
        "texture_data": {f"{namespace}:probe": {"textures": "textures/blocks/probe"}},
    }
    return files


# ------------------------------------------------------------------- pivot --
#
# The rotation probe settled the sign with every bar turning about the block
# centre, where both pivot mappings in issue #52 collapse to the same point. Off
# centre they diverge, and they diverge in opposite directions, so one look
# settles it. Both blocks below carry the same confirmed cube transform and the
# same confirmed sign; the pivot mapping is the only thing they disagree about.
#
# Candidate A mirrors the pivot the way the cube origin is mirrored, on the
# reading that pivot and cube live in one space.
# Candidate B leaves the pivot in Java's unmirrored space.

PIVOTS = ("mirrored", "unmirrored")

# Where Java puts the probe cube: a 4x4x4 block centre cube turned +45 about z
# around [0, 8, 8], which lifts it to about y 13.7 and slides it west to
# about x 5.7. High and slightly west of centre, near the top face.
PIVOT_EXPECTED = "high up, just west of centre"


def pivot_cube(element: dict, mapping: str) -> dict:
    """A rotated element as a Bedrock cube, under one reading of the pivot."""
    cube = _cube(element, "mirrored")
    rotation = element.get("rotation") or {}
    angle = float(rotation.get("angle", 0))
    axis = str(rotation.get("axis", "z"))
    origin = [float(v) for v in rotation.get("origin", [8, 8, 8])]

    degrees = [0.0, 0.0, 0.0]
    # The signs are settled: x and y negate, z is as written.
    sign = {"x": -1.0, "y": -1.0, "z": 1.0}[axis]
    degrees[_JAVA_AXIS_INDEX[axis]] = angle * sign

    x = 8 - origin[0] if mapping == "mirrored" else origin[0] - 8
    cube["pivot"] = [x, origin[1], origin[2] - 8]
    cube["rotation"] = degrees
    return cube


def pivot_pack_files(
    model_file: Path, texture_file: Path, namespace: str
) -> dict[str, object]:
    """Two blocks, one question: which way does an off-centre pivot map?"""
    model = json.loads(model_file.read_text())
    if not model.get("elements"):
        raise ValueError(f"{model_file} has no elements to probe with")
    if not any((e.get("rotation") or {}).get("origin", [8, 8, 8]) != [8, 8, 8]
               for e in model["elements"]):
        raise ValueError(f"{model_file} turns about the centre, so it probes nothing")

    files: dict[str, object] = {}
    labels = []
    for mapping in PIVOTS:
        name = f"pivot_{mapping}"
        identifier = f"geometry.{namespace}.{name}"
        files[f"models/blocks/{name}.geo.json"] = {
            "format_version": _GEOMETRY_FORMAT,
            "minecraft:geometry": [
                {
                    "description": {
                        "identifier": identifier,
                        "texture_width": 16,
                        "texture_height": 16,
                        "visible_bounds_width": 3,
                        "visible_bounds_height": 3,
                        "visible_bounds_offset": [0, 0.75, 0],
                    },
                    "bones": [
                        {
                            "name": "root",
                            "pivot": [0, 0, 0],
                            "cubes": [
                                pivot_cube(e, mapping) for e in model["elements"]
                            ],
                        }
                    ],
                }
            ],
        }
        files[f"blocks/{name}.json"] = block(
            namespace, name, identifier, f"{namespace}:probe"
        )
        title = "A pivot mirrored" if mapping == "mirrored" else "B pivot as written"
        labels.append(
            f"tile.{namespace}:{name}.name={title} (Java: {PIVOT_EXPECTED})"
        )

    files["texts/en_US.lang"] = "\n".join(labels + [""])
    files["textures/blocks/probe.png"] = texture_file.read_bytes()
    files["textures/terrain_texture.json"] = {
        "resource_pack_name": namespace,
        "texture_name": "atlas.terrain",
        "texture_data": {f"{namespace}:probe": {"textures": "textures/blocks/probe"}},
    }
    return files


# --- issue #64: which uv face key does a one-sided face need after the mirror?
#
# The cube origin is mirrored in X (settled by the axis probe) and so is a
# rotation pivot (#52). Built-in face material instances follow the mirror too
# (Java west -> Bedrock east), but cube() writes per-face uv entries under the
# Java face name. A face only exists where a uv entry names it, so for a slab
# textured on one side the key decides which way that face points.
FACE_KEYS = ("mirrored", "aswritten")
FACE_EXPECTED = (
    "a slab on one edge, textured on its outer face only: you see the texture "
    "from outside that edge, and nothing from the opposite side"
)

# Java: a 2-pixel slab against the west edge, drawn on its west face only.
_FACE_ELEMENT = {
    "from": [0, 0, 0],
    "to": [2, 16, 16],
    "faces": {"west": {"uv": [0, 0, 16, 16], "texture": "#probe"}},
}


def _probe_png() -> bytes:
    """A 16x16 opaque texture: orange with a dark border, so the face reads at a glance."""
    import struct
    import zlib

    rows = []
    for y in range(16):
        row = bytearray([0])
        for x in range(16):
            edge = x in (0, 15) or y in (0, 15)
            row += bytes((40, 30, 20, 255) if edge else (235, 140, 30, 255))
        rows.append(bytes(row))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))

    header = struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def face_cube(keying: str) -> dict:
    """The slab as a Bedrock cube, its one uv entry keyed one of two ways."""
    cube = _cube(_FACE_ELEMENT, "mirrored")
    if keying == "mirrored":
        cube["uv"] = {"east": cube["uv"].pop("west")}
    return cube


def face_pack_files(namespace: str) -> dict[str, object]:
    """Two blocks, one question: which face key points a one-sided face outward?"""
    files: dict[str, object] = {}
    labels = []
    for keying in FACE_KEYS:
        name = f"face_{keying}"
        identifier = f"geometry.{namespace}.{name}"
        files[f"models/blocks/{name}.geo.json"] = {
            "format_version": _GEOMETRY_FORMAT,
            "minecraft:geometry": [
                {
                    "description": {
                        "identifier": identifier,
                        "texture_width": 16,
                        "texture_height": 16,
                        "visible_bounds_width": 2,
                        "visible_bounds_height": 2.5,
                        "visible_bounds_offset": [0, 0.75, 0],
                    },
                    "bones": [{"name": "root", "pivot": [0, 0, 0],
                               "cubes": [face_cube(keying)]}],
                }
            ],
        }
        files[f"blocks/{name}.json"] = block(namespace, name, identifier, f"{namespace}:probe")
        title = "A face mirrored" if keying == "mirrored" else "B face as written"
        labels.append(f"tile.{namespace}:{name}.name={title}")

    files["texts/en_US.lang"] = "\n".join(labels + [""])
    files["textures/blocks/probe.png"] = _probe_png()
    files["textures/terrain_texture.json"] = {
        "resource_pack_name": namespace,
        "texture_name": "atlas.terrain",
        "texture_data": {f"{namespace}:probe": {"textures": "textures/blocks/probe"}},
    }
    return files



# Issue #68: a seat turned by a blockstate y turn without uvlock carries its top
# and bottom textures round with it, and Bedrock can only say that with a per-
# face uv_rotation (geometry 1.21.0). The docs call uv_rotation clockwise but do
# not say seen from where, and the down face is seen from below. So: a thin slab
# with an arrow on its top and bottom, unturned (C) and turned each way (A, B).
TURNS = {"control": 0, "cw90": 90, "cw270": 270}
TURN_EXPECTED = (
    "seen from above, the block whose arrow is a quarter turn clockwise from C's; "
    "seen from below, the block whose arrow is a quarter turn anticlockwise from C's"
)
_TURN_GEOMETRY_FORMAT = "1.21.0"
_TURN_ELEMENT = {"from": [0, 0, 0], "to": [16, 4, 16]}


def _arrow_png() -> bytes:
    """16x16: pale ground, a dark arrow pointing at the texture's top edge, and a
    red mark in the top-left corner so a flip shows up as well as a turn."""
    import struct
    import zlib

    def colour(x: int, y: int) -> tuple:
        if x <= 2 and y <= 2:
            return (200, 30, 30, 255)
        head = 1 <= y <= 6 and abs(x - 7.5) <= (y - 1) + 0.5
        shaft = 6 <= y <= 14 and x in (7, 8)
        return (30, 30, 40, 255) if head or shaft else (230, 220, 190, 255)

    rows = []
    for y in range(16):
        row = bytearray([0])
        for x in range(16):
            row += bytes(colour(x, y))
        rows.append(bytes(row))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))

    header = struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def turn_cube(degrees: int) -> dict:
    """The slab with the whole arrow texture on its top and bottom faces."""
    cube = {"origin": [-8.0, 0.0, -8.0], "size": [16.0, 4.0, 16.0], "uv": {}}
    for face in ("up", "down"):
        entry = {"uv": [0.0, 0.0], "uv_size": [16.0, 16.0]}
        if degrees:
            entry["uv_rotation"] = degrees
        cube["uv"][face] = entry
    return cube


def turn_pack_files(namespace: str) -> dict[str, object]:
    """Three blocks: which uv_rotation turns a top (and a bottom) texture the way
    a Java y turn does?"""
    files: dict[str, object] = {}
    labels = []
    titles = {"control": "C unturned", "cw90": "A uv_rotation 90", "cw270": "B uv_rotation 270"}
    for key, degrees in TURNS.items():
        name = f"turn_{key}"
        identifier = f"geometry.{namespace}.{name}"
        files[f"models/blocks/{name}.geo.json"] = {
            "format_version": _TURN_GEOMETRY_FORMAT,
            "minecraft:geometry": [
                {
                    "description": {
                        "identifier": identifier,
                        "texture_width": 16,
                        "texture_height": 16,
                        "visible_bounds_width": 2,
                        "visible_bounds_height": 2.5,
                        "visible_bounds_offset": [0, 0.75, 0],
                    },
                    "bones": [{"name": "root", "pivot": [0, 0, 0], "cubes": [turn_cube(degrees)]}],
                }
            ],
        }
        files[f"blocks/{name}.json"] = block(namespace, name, identifier, f"{namespace}:arrow")
        labels.append(f"tile.{namespace}:{name}.name={titles[key]}")

    files["texts/en_US.lang"] = "\n".join(labels + [""])
    files["textures/blocks/arrow.png"] = _arrow_png()
    files["textures/terrain_texture.json"] = {
        "resource_pack_name": namespace,
        "texture_name": "atlas.terrain",
        "texture_data": {f"{namespace}:arrow": {"textures": "textures/blocks/arrow"}},
    }
    return files
