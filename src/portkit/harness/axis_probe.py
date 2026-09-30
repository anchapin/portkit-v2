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
                f"tile.{namespace}:{name}.name={axis.upper()} {written} (+22.5 about {axis.upper()})"
                if sign == "aswritten"
                else f"tile.{namespace}:{name}.name={axis.upper()} negated (-22.5 about {axis.upper()})"
            )

    files["texts/en_US.lang"] = "\n".join(labels + [""])
    files["textures/blocks/probe.png"] = texture_file.read_bytes()
    files["textures/terrain_texture.json"] = {
        "resource_pack_name": namespace,
        "texture_name": "atlas.terrain",
        "texture_data": {f"{namespace}:probe": {"textures": "textures/blocks/probe"}},
    }
    return files
