"""Java model files, read as far as we can trust them.

Java and Bedrock both describe a block as boxes with UVs, so the vanilla
parents are a lookup, not an inference: cube_all wears one texture on every
face, cube_column wears `end` on the caps and `side` around the middle. Those
resolve to Bedrock's built-in full-block geometry, which is exact.

Two things this module deliberately does NOT do.

It does not follow a parent into vanilla. `minecraft:block/cube_all` is a name
we know the meaning of; a mod model whose parent is some other vanilla model we
have not tabulated is a refusal, not a guess.

It does convert `elements` into custom geometry, but only the plain ones. A
rotated element, or one whose faces wear different textures, still goes to the
residue: each needs its own verification, and a model that loads while quietly
wrong is the failure mode this project exists to avoid.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..model import SourceMod
from .textures import JAVA_DIRS, shortname as texture_key

# Java model parent -> which Bedrock material instance face wears which of the
# model's texture keys. "*" is every face the more specific keys do not name.
PARENTS: dict[str, dict[str, str]] = {
    "minecraft:block/cube_all": {"*": "all"},
    "minecraft:block/cube_column": {"up": "end", "down": "end", "*": "side"},
    "minecraft:block/cube_column_horizontal": {"up": "end", "down": "end", "*": "side"},
    "minecraft:block/cube_bottom_top": {"up": "top", "down": "bottom", "*": "side"},
    "minecraft:block/cube": {
        "up": "up", "down": "down", "north": "north",
        "south": "south", "east": "east", "west": "west",
    },
    # Only reachable from a stateless blockstate, where "front" really is north.
    "minecraft:block/orientable": {
        "up": "top", "down": "top", "north": "front", "*": "side",
    },
    "minecraft:block/orientable_with_bottom": {
        "up": "top", "down": "bottom", "north": "front", "*": "side",
    },
    # #236: vanilla's cube_top and orientable_vertical are full cubes too
    # (block/cube with these face variables; mcmeta summaries 1.16.5-26.3).
    "minecraft:block/cube_top": {"up": "top", "*": "side"},
    "minecraft:block/orientable_vertical": {"up": "front", "*": "side"},
}

_MAX_PARENT_DEPTH = 8

# Bedrock's X axis runs opposite Java's, so a box's origin is measured from the
# far edge: origin.x = 8 - to.x, not from.x - 8. Both readings produce a model
# that loads and renders, and on a symmetric shape they are indistinguishable,
# which is how a mirrored port ships unnoticed. No specification states which
# way round it is, so it was settled by observation: the axis probe harness
# (`portkit probe`) puts both candidates in one pack, and on 2026-09-30 Alex
# Chapin placed them in Bedrock on Android and reported that the mirrored
# candidate is the one matching the Java render. Re-run the probe before
# trusting this on a new Bedrock version.
X_AXIS_IS_FLIPPED = True

# Java element rotation is the plain right-hand rule about the named axis, with
# x east, y up, z south. Anchored on vanilla's wall torch, which rotates -22.5
# about z and leans east away from the west wall it hangs on: only a
# right-handed reading puts it there. See docs/rotation-convention.md for the
# arithmetic and the source files. This describes JAVA, so it does not need a
# Bedrock probe to confirm; what Bedrock does with the sign is a separate
# question the rotation probe answers.
JAVA_ROTATION_IS_RIGHT_HANDED = True

# How a Java element rotation has to be signed to look the same in Bedrock.
# Java's own convention is the right-hand rule (above); what Bedrock does with
# the same angle is a separate question no specification answers, so it was
# settled by observation: the rotation probe (`portkit probe --kind rotation`)
# puts both readings of each axis in one pack, and on 2026-09-30 Alex Chapin
# placed them in Bedrock on Android and reported that x and y match Java only
# when negated, while z matches as written. Re-run the probe before trusting
# this on a new Bedrock version.
#
# Worth knowing: this is not the pattern a plain mirrored X axis would predict
# (that would negate y and z and leave x alone), so the three axes are recorded
# as three separate observations rather than derived from one rule. If a
# converted mod ever leans wrong, suspect this table first.
ROTATION_SIGN = {"x": -1.0, "y": -1.0, "z": 1.0}

# Java only writes these; anything else is a model we have not seen.
_ALLOWED_ANGLES = (-45.0, -22.5, 0.0, 22.5, 45.0)

# Where a Java rotation origin lands in Bedrock geometry. Issue #52 had two
# candidates that agree at the block centre and nowhere else: A mirrors the
# pivot the way the cube origin is mirrored, [8-ox, oy, oz-8]; B leaves it in
# Java's space, [ox-8, oy, oz-8]. The pivot probe (`portkit probe --kind pivot`)
# turned one cube +45 about z around [0, 8, 8] under both. Read in game on
# Bedrock for Android by the project owner, 2026-10-01: "pivot mirrored".
# So pivot and cube share one space, which is what you would hope.
PIVOT_IS_MIRRORED = True

_CENTRE_ORIGIN = (8.0, 8.0, 8.0)
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# A cube in Bedrock geometry is centred on the block: Java's 0..16 becomes
# -8..8 on X and Z, while Y stays as-is.
_HALF = 8.0


def normalize(reference: str) -> str:
    """Java resolves an unprefixed reference against the vanilla namespace."""
    return reference if ":" in reference else f"minecraft:{reference}"


def model_path(mod: SourceMod, reference: str) -> Path | None:
    """Where this mod keeps the model a reference names, if it is ours at all."""
    if ":" in reference:
        namespace, rel = reference.split(":", 1)
        if namespace != mod.namespace:
            return None
    else:
        rel = reference
    return mod.assets / "models" / f"{rel}.json"


def resolve(mod: SourceMod, model: dict) -> tuple[dict, list[Path], str]:
    """Flatten a model against its parent chain inside this mod.

    Mods routinely define their own base model that extends a vanilla parent,
    so reading only the leaf misses both the textures and the real parent.
    Returns the flattened model, the extra files read, and a refusal reason.
    """
    textures: dict = {}
    seen: list[Path] = []
    current = model
    for _ in range(_MAX_PARENT_DEPTH):
        textures = {**(current.get("textures") or {}), **textures}
        parent = current.get("parent")
        if not isinstance(parent, str):
            return _unfolded({**current, "textures": textures}, seen)
        parent = normalize(parent)
        if parent.startswith("minecraft:"):
            # Vanilla: either one of the shapes we have tabulated, or a refusal
            # for faces() to explain. Either way the chain stops here.
            return _unfolded({**current, "parent": parent, "textures": textures}, seen)

        path = model_path(mod, parent)
        if path is None:
            return {}, seen, f"model extends {parent!r}, a model from another namespace"
        if not path.is_file():
            return {}, seen, f"model extends {parent!r}, which is not in this mod"
        seen.append(path)
        try:
            current = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            return {}, seen, f"parent model {parent!r} is invalid JSON: {exc}"
    return {}, seen, "model parent chain is deeper than we follow"


def _unfolded(flat: dict, seen: list[Path]) -> tuple[dict, list[Path], str]:
    """A flattened model with any negative-size element unfolded (see
    unfold_negative), so every reader downstream sees from <= to."""
    elements = flat.get("elements")
    if not isinstance(elements, list) or not elements:
        return flat, seen, ""
    unfolded, why = unfold_elements(elements)
    if unfolded is None:
        return {}, seen, why
    return {**flat, "elements": unfolded}, seen, ""


def faces(model: dict) -> tuple[dict[str, str] | None, str]:
    """The face -> texture-key map for a flattened model, or why there is none."""
    parent = model.get("parent")
    mapped = PARENTS.get(parent) if isinstance(parent, str) else None
    if mapped is not None:
        return mapped, ""

    elements = model.get("elements")
    if isinstance(elements, list) and elements:
        return None, (
            f"model is built from {len(elements)} custom element(s); Bedrock needs a "
            "geometry file and the axis convention is unverified, so converting it "
            "would risk a mirrored model that still loads"
        )
    if parent is None:
        return None, "model has no parent and no elements"
    return None, f"model parent {parent!r} is not a full cube"


def _rotation(element: dict) -> tuple[dict | None, str]:
    """The Bedrock pivot and degrees for a Java element rotation, or why not."""
    spec = element.get("rotation")
    if not spec:
        return {}, ""
    if not isinstance(spec, dict):
        return None, "element has an unreadable rotation"

    axis = spec.get("axis")
    if axis not in _AXIS_INDEX:
        return None, f"element rotates about {axis!r}, which is not an axis"
    try:
        angle = float(spec.get("angle", 0))
        origin = [float(v) for v in spec.get("origin", _CENTRE_ORIGIN)]
    except (TypeError, ValueError):
        return None, "element has an unreadable rotation angle or origin"
    if len(origin) != 3:
        return None, "element rotation origin is not three numbers"
    if angle not in _ALLOWED_ANGLES:
        return None, (
            f"element rotates by {angle} degrees, which Java does not write and "
            "we have not checked against Bedrock"
        )
    degrees = [0.0, 0.0, 0.0]
    degrees[_AXIS_INDEX[axis]] = angle * ROTATION_SIGN[axis]
    pivot_x = _HALF - origin[0] if PIVOT_IS_MIRRORED else origin[0] - _HALF
    pivot = [pivot_x, origin[1], origin[2] - _HALF]
    return {"pivot": pivot, "rotation": degrees}, ""


def cube(element: dict, tag_faces: bool = False) -> tuple[dict | None, str]:
    """One Java element as a Bedrock geometry cube, or why it cannot be one.

    With tag_faces, every face also names its material instance (see
    tagged_materials), which is how one block wears different textures on
    faces that point the same way.
    """
    turn, reason = _rotation(element)
    if turn is None:
        return None, reason

    try:
        x1, y1, z1 = (float(v) for v in element["from"])
        x2, y2, z2 = (float(v) for v in element["to"])
    except (KeyError, TypeError, ValueError):
        return None, "element is missing usable from/to coordinates"
    if x2 < x1 or y2 < y1 or z2 < z1:
        return None, "element has a negative size"

    origin_x = _HALF - x2 if X_AXIS_IS_FLIPPED else x1 - _HALF
    box = {
        "origin": [origin_x, y1, z1 - _HALF],
        "size": [x2 - x1, y2 - y1, z2 - z1],
    }

    uv: dict[str, dict] = {}
    for face, spec in (element.get("faces") or {}).items():
        if not isinstance(spec, dict):
            continue
        corners = spec.get("uv")
        if not (isinstance(corners, list) and len(corners) == 4):
            if tag_faces and isinstance(spec.get("texture"), str):
                return None, (
                    f"element's {face} face has no uv, and naming its material "
                    "in the geometry needs one"
                )
            continue
        try:
            u1, v1, u2, v2 = (float(v) for v in corners)
        except (TypeError, ValueError):
            return None, f"element has an unreadable uv on its {face} face"
        uv[face] = {"uv": [u1, v1], "uv_size": [u2 - u1, v2 - v1]}
        face_turn, why = _face_turn(face, spec.get("rotation"))
        if face_turn is None:
            return None, why
        if face_turn:
            uv[face]["uv_rotation"] = face_turn
        reference = spec.get("texture")
        if tag_faces and isinstance(reference, str):
            uv[face]["material_instance"] = instance_name(reference.lstrip("#"))
    if uv:
        box["uv"] = uv
    box.update(turn)
    return box, ""


# Issue #68, read in game on Bedrock for Android, 2026-10-02 (`portkit probe
# --kind turn`): uv_rotation 90 turned the top texture a quarter turn clockwise
# seen from above, and the bottom texture clockwise seen from below (270 read as
# anticlockwise from below), with nothing mirrored. So on the top and bottom
# faces uv_rotation is clockwise seen from outside the face, which is how Java's
# own per-face "rotation" is defined, and the number carries straight across.
# Issue #71, read in game the same way on 2026-10-02 (`portkit probe --kind
# sideturn`): uv_rotation 90 on a side face turned its texture a quarter turn
# clockwise looking straight at that face, on all four sides (east and west
# included, so the X mirror does not reverse them), with nothing mirrored. Side
# faces follow the same rule, and every face's rotation carries straight across.
_TURNABLE_FACES = ("up", "down", "north", "south", "east", "west")


def _face_turn(face: str, rotation) -> tuple[int | None, str]:
    if rotation in (None, 0):
        return 0, ""
    try:
        degrees = int(rotation) % 360
    except (TypeError, ValueError):
        return None, f"element's {face} face has an unreadable texture rotation"
    if degrees % 90:
        return None, f"element's {face} face turns its texture {rotation} degrees"
    if degrees and face not in _TURNABLE_FACES:
        return None, (
            f"element's {face} face turns its texture {degrees} degrees, and which "
            "way Bedrock turns a side face has not been checked in game"
        )
    return degrees, ""


_MIRRORED_FACES = {"west": "east", "east": "west"}

# Whether a face name has to swap west/east to follow the X mirror. Issue #64:
# the face probe (`portkit probe --kind face`) built a slab on one edge, drawn
# on one face only, keyed both ways. Read in game on Bedrock for Android by the
# project owner, 2026-10-01: "B face as written". So once the box is mirrored,
# the face Bedrock calls west is the one Java calls west, and names carry over.
# The probe keyed the per-face uv entry; built-in face material instances bind
# to those same named faces, so they follow the same rule.
FACE_NAMES_FOLLOW_MIRROR = False


def element_materials(model: dict) -> tuple[dict[str, str] | None, str]:
    """Bedrock material-instance name -> Java texture key, for a custom shape.

    Bedrock ships seven built-in material instances: "*" plus one per cube face
    (down, up, north, south, west, east). They bind to cube faces on their own,
    with no per-face uv block and no names invented in the geometry, so a beam
    wearing "end" on its caps and "side" on its flanks needs nothing but the
    right keys on the block definition.

    Face names carry over unchanged: the face probe (#64) showed that after
    cube() mirrors the box, Bedrock's west face is still Java's west face.
    """
    elements = model.get("elements") or []
    if not elements:
        return None, "model has no elements"

    by_face: dict[str, set[str]] = {}
    for element in elements:
        for face, spec in (element.get("faces") or {}).items():
            if not isinstance(spec, dict):
                continue
            reference = spec.get("texture")
            if not isinstance(reference, str):
                continue
            target = _MIRRORED_FACES.get(face, face) if FACE_NAMES_FOLLOW_MIRROR else face
            by_face.setdefault(target, set()).add(reference.lstrip("#"))

    if not by_face:
        return None, "element faces name no texture"

    disagreeing = sorted(face for face, keys in by_face.items() if len(keys) > 1)
    if disagreeing:
        return None, (
            f"elements disagree about the texture on their {', '.join(disagreeing)} "
            "face(s), and one block carries one material per face"
        )
    return {face: keys.pop() for face, keys in by_face.items()}, ""


_BUILT_IN_INSTANCES = {"*", "up", "down", "north", "south", "east", "west"}


def instance_name(texture_key: str) -> str:
    """The material-instance name a Java texture key gets in the geometry.

    The key itself, so a pack reads like its mod, unless it collides with one
    of Bedrock's seven built-in instances, which bind to faces on their own.
    """
    return f"java_{texture_key}" if texture_key in _BUILT_IN_INSTANCES else texture_key


def tagged_materials(model: dict) -> tuple[dict[str, str] | None, str]:
    """Material-instance name -> Java texture key, for faces that disagree.

    element_materials covers a model whose elements agree per face direction.
    When they don't (a bonfire's logs and its flame cross both face east and
    west), the built-in per-face instances cannot tell them apart, so each face
    names its instance in the geometry instead: one per texture key, bound on
    the block. Pair with geometry(..., tag_faces=True).
    """
    keys: set[str] = set()
    for element in model.get("elements") or []:
        for spec in (element.get("faces") or {}).values():
            if isinstance(spec, dict) and isinstance(spec.get("texture"), str):
                keys.add(spec["texture"].lstrip("#"))
    if not keys:
        return None, "element faces name no texture"
    return {instance_name(key): key for key in sorted(keys)}, ""


def element_texture(model: dict) -> tuple[str | None, str]:
    """The one texture key every element face wears, or why there isn't one."""
    references = set()
    for element in model.get("elements") or []:
        for spec in (element.get("faces") or {}).values():
            if isinstance(spec, dict) and isinstance(spec.get("texture"), str):
                references.add(spec["texture"].lstrip("#"))
    if not references:
        return None, "element faces name no texture"
    if len(references) > 1:
        names = ", ".join(sorted(references))
        return None, (
            f"element faces wear different textures ({names}); per-face geometry "
            "materials are not mapped yet"
        )
    return references.pop(), ""


def geometry(model: dict, identifier: str, tag_faces: bool = False) -> tuple[dict | None, str]:
    """A Bedrock geometry file for a model's elements, or why there is none."""
    elements = model.get("elements") or []
    if not elements:
        return None, "model has no elements"
    return geometry_bones([("root", elements)], identifier, tag_faces)


def geometry_bones(
    parts: list[tuple[str, list]], identifier: str, tag_faces: bool = False
) -> tuple[dict | None, str]:
    """A geometry file with one named bone per part, so bone_visibility can
    switch parts on and off the way a Java multipart blockstate does."""
    bones = []
    for name, elements in parts:
        elements, why = unfold_elements(elements)
        if elements is None:
            return None, f"{name}: {why}"
        cubes = []
        for element in elements:
            box, why = cube(element, tag_faces)
            if box is None:
                return None, f"{name}: {why}"
            cubes.append(box)
        bones.append({"name": name, "pivot": [0, 0, 0], "cubes": cubes})

    # Per-face uv_rotation arrived with geometry 1.21.0; everything else stays
    # on 1.16.0 so existing output is unchanged.
    turned = any(
        "uv_rotation" in entry
        for bone in bones for box in bone["cubes"] for entry in (box.get("uv") or {}).values()
    )
    return {
        "format_version": "1.21.0" if turned else "1.16.0",
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
                "bones": bones,
            }
        ],
    }, ""


def texture_shortname(reference: str, namespace: str) -> tuple[str | None, str]:
    """Java texture reference -> the terrain_texture shortname the pack uses.

    The textures converter keys its index as "<namespace>:<subpath>", the path
    below block/ or item/ with "/" and "-" flattened to "_", so a reference into this
    mod resolves. A reference into another namespace
    (vanilla, or a sibling mod) does not: Bedrock's own shortnames are named
    differently and picking one would be a guess.
    """
    if reference.startswith("#"):
        return None, f"model leaves {reference!r} for a child model to fill in"
    # A bare reference is minecraft:'s, as Java resolves it, not the mod's own.
    ref_ns, _, path = reference.rpartition(":")
    ref_ns = ref_ns or "minecraft"
    if ref_ns != namespace:
        return None, f"model points at {reference!r}, a texture from another namespace"
    lane, _, subpath = path.partition("/")
    if lane not in JAVA_DIRS or not subpath:
        # Not a texture the textures converter places (entity/, gui/, a
        # pre-1.13 blocks/ dir); keep the old stem key so the miss is reported.
        subpath = path.rsplit("/", 1)[-1]
    return texture_key(subpath, namespace), ""


def texture_file(reference: str, namespace: str) -> tuple[str | None, str]:
    """Java texture reference -> the pack path (no extension) the textures
    converter writes it to, for files that name a texture by path (an
    attachable) rather than by atlas key. Only this mod's block and item
    textures, the lanes the textures converter places."""
    if reference.startswith("#"):
        return None, f"model leaves {reference!r} for a child model to fill in"
    ref_ns, _, path = reference.rpartition(":")
    if (ref_ns or "minecraft") != namespace:
        return None, f"model points at {reference!r}, a texture from another namespace"
    lane, _, subpath = path.partition("/")
    bedrock = {"block": "textures/blocks", "blocks": "textures/blocks",
               "item": "textures/items", "items": "textures/items"}.get(lane)
    if bedrock is None or not subpath:
        return None, f"model points at {reference!r}, outside the block and item textures"
    return f"{bedrock}/{subpath}", ""


# Java's texture dirs -> the vanilla Bedrock dir with the same files and the
# atlas that indexes it. Pre-1.13 mods named the Java dirs blocks/ and items/.
_VANILLA_DIRS = {
    "block": ("textures/blocks/", "terrain"), "blocks": ("textures/blocks/", "terrain"),
    "item": ("textures/items/", "item"), "items": ("textures/items/", "item"),
}

# Pick 2 (PR #220): a Java name that is a vanilla short name showing a file of
# another name (oak_planks -> textures/blocks/planks_oak). Off: such a name
# stays residue, since Bedrock's short names are not always Java's texture
# (Bedrock's piston_top shows textures/blocks/piston_inner).
MAP_RENAMED = False


def is_vanilla(reference: str, namespace: str) -> bool:
    """Is this texture reference into vanilla (minecraft:, or bare) from a mod?"""
    if not isinstance(reference, str) or reference.startswith("#"):
        return False
    ref_ns, _, _ = reference.rpartition(":")
    return (ref_ns or "minecraft") == "minecraft" and namespace != "minecraft"


def vanilla_texture(
    reference: str, namespace: str, atlas: str = "terrain",
) -> tuple[str | None, str | None, str]:
    """A vanilla Java texture -> how the Bedrock pack names Bedrock's own copy.

    Returns (key, file, why). ``key`` is what a material instance (atlas
    "terrain") or an item icon (atlas "item") names. ``file`` is None when the
    key is a vanilla short name, which the vanilla atlas already defines (the
    pack's atlas is merged with it); otherwise the pack's atlas needs an entry
    ``key -> file`` pointing at the vanilla file, which the vanilla pack below
    serves. No art is copied either way.

    The rule is the file's name (pick 1): Java's ``block/<name>`` is Bedrock's
    ``textures/blocks/<name>``, the same texture under the same name. A vanilla
    short name showing just that file is named directly; a file the atlas only
    lists inside a set of variants gets the pack entry (pick 3), unless vanilla
    animates it (a flipbook keyed to vanilla's own short name; an entry of ours
    would show the whole strip). Everything else stays residue with the reason.
    """
    from ..data import vanilla_textures

    _, _, path = reference.rpartition(":")
    lane, _, name = path.partition("/")
    if lane not in _VANILLA_DIRS or not name:
        return None, None, f"model points at {reference!r}, a vanilla texture outside block/ and item/"
    index = vanilla_textures.index()
    if index is None:
        return None, None, (
            f"model points at {reference!r}, a vanilla texture; Bedrock's vanilla texture "
            f"index isn't cached (run `portkit reference fetch`)"
        )
    folder, home = _VANILLA_DIRS[lane]
    file = folder + name
    # pipeline.vanilla_entries reads the file back off this key
    entry_key = f"{namespace}:vanilla/{'block' if home == 'terrain' else 'item'}/{name}"
    animated = index.animated.get(file)
    if file in index.files[home]:
        if atlas == home:
            names = index.sole[home].get(file) or []
            if animated:
                names = [n for n in names if n in animated]
            if names:
                return (name if name in names else names[0]), None, ""
        if animated:
            return None, None, (
                f"model points at {reference!r}, a vanilla texture Bedrock animates ({file}) "
                f"through vanilla's flipbook for {', '.join(animated)}, which a pack entry of "
                f"its own would lose"
            )
        return entry_key, file, ""
    renamed = (index.atlases[home].get(name) or {}).get("paths") or []
    if len(renamed) == 1:
        if (MAP_RENAMED and atlas == home and index.atlases[home][name].get("plain")
                and not index.animated.get(renamed[0])):
            return name, None, ""
        return None, None, (
            f"model points at {reference!r}, a vanilla texture: Bedrock has no {file}; its "
            f"short name {name!r} shows {renamed[0]}, a file of another name, so it is not mapped"
        )
    if renamed:
        return None, None, (
            f"model points at {reference!r}, a vanilla texture: Bedrock has no {file}; its "
            f"short name {name!r} is a set of {len(renamed)} textures, and which one Java's is "
            f"isn't named"
        )
    return None, None, (
        f"model points at {reference!r}, a vanilla texture: Bedrock's vanilla pack has no "
        f"texture of that name ({file})"
    )


# A Java blockstate y turn spins the model clockwise seen from above, in Java's
# own coordinates, before any Bedrock conversion. Each quarter turn sends a
# point (x, z) to (16 - z, x) and a north face to east.
_Y_TURN_FACES = {"north": "east", "east": "south", "south": "west", "west": "north"}


def auto_uv(face: str, start: list, end: list) -> list[float]:
    """The uv Java derives from an element's position when a face names none.

    This is also exactly what uvlock produces for an unrotated element: the
    texture stays fixed to the world while the box moves through it.
    """
    x1, y1, z1 = (float(v) for v in start)
    x2, y2, z2 = (float(v) for v in end)
    return {
        "down": [x1, 16 - z2, x2, 16 - z1],
        "up": [x1, z1, x2, z2],
        "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
        "south": [x1, 16 - y2, x2, 16 - y1],
        "west": [z1, 16 - y2, z2, 16 - y1],
        "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1],
    }[face]


# --------------------------------------------------------------------------
# Negative-size elements. Java does not sort an element's corners: the model
# deserializer only checks each coordinate lies in [-16, 32]
# (BlockElement$Deserializer#getFrom/getTo L147-163), and FaceBakery#setupShape
# (L114-121) files `from` under MIN_X/MIN_Y/MIN_Z and `to` under MAX_X/MAX_Y/
# MAX_Z as written. Each face's four vertices are then read from those six
# numbers through FaceInfo (FaceInfo <clinit> L7-32), vertex i taking
# BlockFaceUV#getU(i)/getV(i) (L25-38). So on an axis where from > to, a face
# keyed to that axis's minimum lands on the larger coordinate, and a face whose
# in-plane axis is swapped is wound the other way round. FaceBakery#bakeQuad
# (L49) then names the quad by the way it really faces (calculateFacing
# L198-223: (v2 - v1) x (v0 - v1), nearest Direction), which is the side it is
# drawn on. Blockbench's "inverted" cubes rely on this: their faces point in.
# All MC 1.21.1 client jar, Mojang mappings.
#
# unfold_negative rewrites such an element as ordinary elements Java bakes to
# the very same quads (same corners, same uv at each corner): a face pointing
# out of the sorted box stays on that box under the name it really faces; a
# face pointing into it becomes a zero-thickness element on its plane.
# FaceInfo vertex corners: per face, four (x, y, z) picks, 0 = MIN (from), 1 = MAX (to).
_FACE_INFO = {
    "down": ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)),
    "up": ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
    "north": ((1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0)),
    "south": ((0, 1, 1), (0, 0, 1), (1, 0, 1), (1, 1, 1)),
    "west": ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)),
    "east": ((1, 1, 1), (1, 0, 1), (1, 0, 0), (1, 1, 0)),
}
NEGATIVE_MARK = "portkit_negative"
# uvlock (FaceBakery#recomputeUVs L61-102) re-maps a face's uv by the face it
# was declared as, not the way an unfolded face really points, so a turned,
# uvlocked negative-size element is not mapped.
_NEGATIVE_UVLOCK = (
    "uvlock turns a negative-size element, and Java re-maps its uvs by the face "
    "each was declared as (FaceBakery#recomputeUVs), which is not mapped"
)


def baked_quad(face: str, start: list, end: list, uv: list, rotation: int) -> list[tuple]:
    """The four (corner, (u, v)) pairs Java bakes for one element face, from
    the raw ``from``/``to`` (FaceBakery#setupShape, FaceInfo, BlockFaceUV)."""
    shift = (int(rotation) % 360) // 90
    corners = []
    for i, pick in enumerate(_FACE_INFO[face]):
        point = tuple(float(end[a] if hi else start[a]) for a, hi in enumerate(pick))
        k = (i + shift) % 4
        u = uv[0] if k in (0, 1) else uv[2]
        v = uv[1] if k in (0, 3) else uv[3]
        corners.append((point, (float(u), float(v))))
    return corners


def quad_facing(corners: list[tuple]) -> str | None:
    """FaceBakery#calculateFacing: the face a quad's winding points out of."""
    (p0, _), (p1, _), (p2, _) = corners[0], corners[1], corners[2]
    a = [p2[i] - p1[i] for i in range(3)]
    b = [p0[i] - p1[i] for i in range(3)]
    n = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    best, score = None, 0.0
    for face, normal in _FACE_NORMAL.items():
        d = sum(n[i] * normal[i] for i in range(3))
        if d > score:
            best, score = face, d
    return best


def _same_quad(a: list[tuple], b: list[tuple]) -> bool:
    def key(corners):
        return sorted((tuple(round(c, 6) for c in p), tuple(round(c, 6) for c in uv)) for p, uv in corners)
    return key(a) == key(b)


def unfold_negative(element: dict) -> tuple[list[dict] | None, str]:
    """``element`` as elements with from <= to that Java renders identically,
    or why not. An element that is not negative comes back alone, untouched."""
    try:
        start = [float(v) for v in element["from"]]
        end = [float(v) for v in element["to"]]
    except (KeyError, TypeError, ValueError):
        return [element], ""
    if len(start) != 3 or len(end) != 3 or all(s <= e for s, e in zip(start, end)):
        return [element], ""
    low = [min(s, e) for s, e in zip(start, end)]
    high = [max(s, e) for s, e in zip(start, end)]
    rest = {k: v for k, v in element.items() if k not in ("from", "to", "faces")}
    rest[NEGATIVE_MARK] = True
    outward: dict = {}
    planes: list[dict] = []
    for face, spec in (element.get("faces") or {}).items():
        if face not in _FACE_INFO:
            return None, f"negative-size element has an unknown {face!r} face"
        if not isinstance(spec, dict):
            return None, f"negative-size element's {face} face is not an object"
        # BlockElement#fillUvs: a face without uv takes uvsByFace of the raw
        # from/to, before anything is sorted.
        corners = spec.get("uv")
        try:
            uv = [float(v) for v in corners] if corners is not None else auto_uv(face, start, end)
            rotation = int(spec.get("rotation") or 0)
        except (TypeError, ValueError):
            return None, f"negative-size element has an unreadable uv or rotation on its {face} face"
        if len(uv) != 4 or rotation % 90:
            return None, f"negative-size element has an unreadable uv or rotation on its {face} face"
        quad = baked_quad(face, start, end, uv, rotation)
        facing = quad_facing(quad)
        if facing is None:
            return None, f"negative-size element's {face} face has no area"
        axis = next(i for i, c in enumerate(_FACE_NORMAL[facing]) if c)
        plane = quad[0][0][axis]
        side = high[axis] if sum(_FACE_NORMAL[facing]) > 0 else low[axis]
        box_lo, box_hi = list(low), list(high)
        if plane != side:
            box_lo[axis] = box_hi[axis] = plane
        found = None
        u0, v0, u1, v1 = uv
        # The uv kept as written where a texture turn (uv_rotation, read in
        # game: #68/#71) reproduces it; a mirrored uv only where one is needed.
        for cand in ([u0, v0, u1, v1], [u1, v0, u0, v1], [u0, v1, u1, v0], [u1, v1, u0, v0]):
            for turn in range(4):
                r = (rotation + 90 * turn) % 360
                if _same_quad(baked_quad(facing, box_lo, box_hi, cand, r), quad):
                    found = (cand, r)
                    break
            if found:
                break
        if found is None:  # pragma: no cover - the square's 8 symmetries are all reached
            return None, f"negative-size element's {face} face has no matching layout"
        new = {k: v for k, v in spec.items() if k != "rotation"}
        new["uv"] = found[0]
        if found[1]:
            new["rotation"] = found[1]
        if plane == side:
            outward[facing] = new
        else:
            planes.append({**rest, "from": box_lo, "to": box_hi, "faces": {facing: new}})
    unfolded = []
    if outward:
        unfolded.append({**rest, "from": low, "to": high, "faces": outward})
    unfolded.extend(planes)
    return unfolded, ""


def unfold_elements(elements: list) -> tuple[list | None, str]:
    """unfold_negative over a model's element list."""
    out: list = []
    for element in elements:
        if not isinstance(element, dict):
            out.append(element)
            continue
        found, why = unfold_negative(element)
        if found is None:
            return None, why
        out.extend(found)
    return out, ""


def _zero_rotation(rotation) -> bool:
    """Whether a Java element ``rotation`` turns by 0 degrees (an identity)."""
    if not isinstance(rotation, dict):
        return False
    try:
        return float(rotation.get("angle", 0)) == 0.0
    except (TypeError, ValueError):
        return False


def turn_y(element: dict, degrees: int, uvlock: bool) -> tuple[dict | None, str]:
    """An element as a Java blockstate y turn leaves it, or why not.

    Only the case we can state exactly is taken: uvlock on, an unrotated
    element, and uvs that are Java's own position-derived ones (or absent).
    Then the turned element simply wears the position-derived uvs of where it
    lands. Without uvlock Java also spins the up/down textures, which is not
    mapped yet.
    """
    if degrees % 90:
        return None, f"y turn of {degrees} degrees is not a quarter turn"
    quarters = (degrees // 90) % 4
    if quarters == 0:
        return element, ""
    if _zero_rotation(element.get("rotation")):
        # A rotation of 0 degrees moves nothing (and its rescale divides by
        # cos 0 = 1): the element is unrotated (Waystones' fleeting memorial).
        element = {k: v for k, v in element.items() if k != "rotation"}
    if element.get("rotation"):
        return None, "part turns a model whose elements are themselves rotated"
    try:
        (x1, y1, z1), (x2, y2, z2) = element["from"], element["to"]
    except (KeyError, TypeError, ValueError):
        return None, "element is missing usable from/to coordinates"
    if not uvlock:
        return _turn_with_textures(element, quarters, [x1, y1, z1], [x2, y2, z2])
    if element.get(NEGATIVE_MARK):
        return None, _NEGATIVE_UVLOCK

    faces = element.get("faces") or {}
    for face, spec in faces.items():
        corners = spec.get("uv") if isinstance(spec, dict) else None
        if corners is not None and [float(v) for v in corners] != auto_uv(face, [x1, y1, z1], [x2, y2, z2]):
            return None, (
                f"part turns a model with a hand-set uv on its {face} face, and uvlock "
                "would replace it in a way that is not mapped yet"
            )

    for _ in range(quarters):
        x1, z1, x2, z2 = 16 - z2, x1, 16 - z1, x2
        faces = {_Y_TURN_FACES.get(f, f): spec for f, spec in faces.items()}
    start, end = [x1, y1, z1], [x2, y2, z2]
    turned = {}
    for face, spec in faces.items():
        spec = dict(spec) if isinstance(spec, dict) else spec
        if isinstance(spec, dict):
            spec["uv"] = auto_uv(face, start, end)
        turned[face] = spec
    return {**element, "from": start, "to": end, "faces": turned}, ""



_SIDES = ("north", "east", "south", "west")


def zero_rotation(rotation) -> bool:
    """Whether an element's ``rotation`` is one Java leaves as it is: an
    object whose angle is 0 (rescale then scales by 1/cos 0 = 1)."""
    if not isinstance(rotation, dict):
        return False
    try:
        return float(rotation.get("angle") or 0) == 0
    except (TypeError, ValueError):
        return False


def split_y(element: dict, at: float) -> tuple[tuple[dict, dict] | None, str]:
    """``element`` cut at height ``at`` into the part below and the part above,
    looking exactly as the whole did, or why not.

    Each side face keeps its texture: its uv's v edge is cut where ``at``
    falls between the top (Java's v1 edge) and the bottom (v2), linearly, as
    Java maps the face's quad. The up face goes with the top part, the down
    face with the bottom one. Only an unrotated element (or one rotated by 0
    degrees, which Java leaves as it is) with unrotated side faces is cut.
    """
    rotation = element.get("rotation")
    if rotation and not zero_rotation(rotation):
        return None, "element is rotated"
    try:
        start = [float(v) for v in element["from"]]
        end = [float(v) for v in element["to"]]
    except (KeyError, TypeError, ValueError):
        return None, "element is missing usable from/to coordinates"
    low, high = sorted((start[1], end[1]))
    if not low < at < high:
        return None, f"element does not cross y={at}"
    below = {k: v for k, v in element.items() if k not in ("rotation", "faces")}
    above = dict(below)
    below["from"], below["to"] = [start[0], low, start[2]], [end[0], at, end[2]]
    above["from"], above["to"] = [start[0], at, start[2]], [end[0], high, end[2]]
    faces_below: dict = {}
    faces_above: dict = {}
    for face, spec in (element.get("faces") or {}).items():
        if not isinstance(spec, dict):
            return None, f"element's {face} face is not an object"
        if face == "up":
            faces_above[face] = dict(spec)
            continue
        if face == "down":
            faces_below[face] = dict(spec)
            continue
        if face not in _SIDES:
            return None, f"element has an unknown {face!r} face"
        if spec.get("rotation"):
            return None, f"element's {face} face is rotated"
        try:
            u1, v1, u2, v2 = (float(v) for v in (spec.get("uv") or auto_uv(face, start, end)))
        except (TypeError, ValueError):
            return None, f"element's {face} face has no usable uv"
        cut = round(v1 + (high - at) / (high - low) * (v2 - v1), 6)
        faces_above[face] = {**spec, "uv": [u1, v1, u2, cut]}
        faces_below[face] = {**spec, "uv": [u1, cut, u2, v2]}
    below["faces"], above["faces"] = faces_below, faces_above
    return (below, above), ""


def _turn_with_textures(element: dict, quarters: int, start: list, end: list) -> tuple[dict | None, str]:
    """A y turn without uvlock: the textures ride along with the box.

    Side faces keep their uv and move to the face they now point out of. The
    top turns clockwise seen from above, which is a Java face rotation of +90
    per quarter on "up" and, seen from below, -90 on "down" (see _face_turn for
    how those reach Bedrock). A face with no uv gets the one Java would have
    derived from where it started.
    """
    x1, y1, z1 = start
    x2, y2, z2 = end
    faces = {}
    for face, spec in (element.get("faces") or {}).items():
        if not isinstance(spec, dict):
            continue
        spec = dict(spec)
        if spec.get("uv") is None:
            spec["uv"] = auto_uv(face, start, end)
        if face in ("up", "down"):
            step = 90 if face == "up" else 270
            spec["rotation"] = (int(spec.get("rotation") or 0) + step * quarters) % 360
        faces[face] = spec
    for _ in range(quarters):
        x1, z1, x2, z2 = 16 - z2, x1, 16 - z1, x2
        faces = {_Y_TURN_FACES.get(f, f): spec for f, spec in faces.items()}
    return {**element, "from": [x1, y1, z1], "to": [x2, y2, z2], "faces": faces}, ""


# --------------------------------------------------------------------------
# Rigid blockstate turns in Java space. A blockstate's x and y turn a shared
# model as a solid object (x first, then y, as Java applies them). Without
# uvlock every face's texture rides along, so the turn is baked into the Java
# element before conversion: the box moves, each face lands on the face its
# normal now points out of, and its texture picks up whatever in-plane turn
# the move gave it. Everything Bedrock-specific (the X mirror, uv_rotation)
# then applies exactly as it does to a model Java baked by hand.
_FACE_NORMAL = {
    "up": (0, 1, 0), "down": (0, -1, 0), "north": (0, 0, -1),
    "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0),
}
# Java's own uv layout per face, seen from outside: where the texture's top
# edge (-v) and its right edge (+u) point in the world.
_FACE_TEX_UP = {
    "up": (0, 0, -1), "down": (0, 0, 1), "north": (0, 1, 0),
    "south": (0, 1, 0), "east": (0, 1, 0), "west": (0, 1, 0),
}
_FACE_TEX_RIGHT = {
    "up": (1, 0, 0), "down": (1, 0, 0), "north": (-1, 0, 0),
    "south": (1, 0, 0), "east": (0, 0, -1), "west": (0, 0, 1),
}


def _turn_vector(v: tuple, x_quarters: int, y_quarters: int) -> tuple:
    """Java blockstate x then y, quarter turns. x=90 sends north to down; y=90
    sends north to east (clockwise seen from above)."""
    vx, vy, vz = v
    for _ in range(x_quarters % 4):
        vx, vy, vz = vx, vz, -vy
    for _ in range(y_quarters % 4):
        vx, vy, vz = -vz, vy, vx
    return (vx, vy, vz)


def _face_for(normal: tuple) -> str:
    return next(f for f, n in _FACE_NORMAL.items() if n == normal)


def _neg(v: tuple) -> tuple:
    return tuple(-c for c in v)


_AXIS_VECTOR = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


def _turned_rotation(rotation, xq: int, yq: int) -> tuple[dict | None, str]:
    """An element rotation carried through a quarter-turn blockstate x/y turn.

    The blockstate turn is rigid and applies to the baked quads after the
    element's own rotation, so turn . rot(axis, angle) = rot(turn(axis),
    angle) . turn: the axis goes where the turn sends it (the angle flips
    sign when it lands on the negative axis, as rot(-a, t) = rot(a, -t)), the
    origin moves with the box, and rescale is unchanged."""
    if not isinstance(rotation, dict) or rotation.get("axis") not in _AXIS_VECTOR:
        return None, "element has an unreadable rotation"
    try:
        angle = float(rotation.get("angle", 0))
        origin = [float(c) for c in rotation.get("origin", (8, 8, 8))]
    except (TypeError, ValueError):
        return None, "element has an unreadable rotation"
    if len(origin) != 3:
        return None, "element has an unreadable rotation"
    vector = _turn_vector(_AXIS_VECTOR[rotation["axis"]], xq, yq)
    axis = "xyz"[next(i for i, c in enumerate(vector) if c)]
    sign = sum(vector)
    moved = [c + _HALF for c in _turn_vector(tuple(c - _HALF for c in origin), xq, yq)]
    out = {**rotation, "axis": axis, "angle": angle * sign if angle else angle,
           "origin": [int(c) if float(c).is_integer() else c for c in moved]}
    if isinstance(rotation.get("angle"), int) and float(out["angle"]).is_integer():
        out["angle"] = int(out["angle"])
    return out, ""


def turn_rigid(element: dict, x_degrees: int, y_degrees: int,
               carry_rotation: bool = False) -> tuple[dict | None, str]:
    """An element as a Java blockstate x/y turn without uvlock leaves it, or why not.

    ``carry_rotation``: a rotated element turns too, its rotation carried by
    _turned_rotation (used by the 6-way / attach-face path); otherwise it is
    refused, as before."""
    if x_degrees % 90 or y_degrees % 90:
        return None, f"blockstate turn x={x_degrees} y={y_degrees} is not in quarter turns"
    xq, yq = (x_degrees // 90) % 4, (y_degrees // 90) % 4
    if not xq and not yq:
        return element, ""
    rotation = None
    if element.get("rotation"):
        if not carry_rotation:
            return None, "blockstate turns a model whose elements are themselves rotated"
        rotation, why = _turned_rotation(element["rotation"], xq, yq)
        if rotation is None:
            return None, why
    try:
        start = [float(c) for c in element["from"]]
        end = [float(c) for c in element["to"]]
    except (KeyError, TypeError, ValueError):
        return None, "element is missing usable from/to coordinates"

    corners = []
    for point in (start, end):
        centred = tuple(c - _HALF for c in point)
        corners.append([c + _HALF for c in _turn_vector(centred, xq, yq)])
    new_start = [min(a, b) for a, b in zip(*corners)]
    new_end = [max(a, b) for a, b in zip(*corners)]

    faces = {}
    for face, spec in (element.get("faces") or {}).items():
        if not isinstance(spec, dict) or face not in _FACE_NORMAL:
            return None, f"element has an unreadable {face} face"
        spec = dict(spec)
        if spec.get("uv") is None:
            spec["uv"] = auto_uv(face, start, end)
        target = _face_for(_turn_vector(_FACE_NORMAL[face], xq, yq))
        up = _turn_vector(_FACE_TEX_UP[face], xq, yq)
        turn = {
            _FACE_TEX_UP[target]: 0,
            _FACE_TEX_RIGHT[target]: 90,
            _neg(_FACE_TEX_UP[target]): 180,
            _neg(_FACE_TEX_RIGHT[target]): 270,
        }[up]
        try:
            base = int(spec.get("rotation") or 0)
        except (TypeError, ValueError):
            return None, f"element's {face} face has an unreadable texture rotation"
        if base or turn:
            spec["rotation"] = (base + turn) % 360
        cull = spec.get("cullface")
        if cull in _FACE_NORMAL:
            spec["cullface"] = _face_for(_turn_vector(_FACE_NORMAL[cull], xq, yq))
        faces[target] = spec
    out = {**element, "from": new_start, "to": new_end, "faces": faces}
    if rotation is not None:
        out["rotation"] = rotation
    return out, ""


# --------------------------------------------------------------------------
# Vanilla templates. A stairs, slab or wall model names a vanilla parent
# (minecraft:block/stairs) and only fills in textures; the boxes are vanilla's.
# portkit reads those parents from the fetched reference set
# (portkit.data.models), never from a copy in the repository.
def is_template(parent: str) -> bool:
    """Whether ``parent`` is one of the vanilla templates portkit fetches by
    name (portkit.data.models.TEMPLATES), as opposed to a chain parent that
    comes along (block/block) or a model it doesn't read."""
    from ..data.models import TEMPLATES

    return parent.startswith("minecraft:") and parent.partition(":")[2] in TEMPLATES


def expand_template(model: dict, minecraft: str | None = None) -> tuple[dict | None, str]:
    """A flattened model with its vanilla template's elements filled in.

    A model that already has elements comes back as it is. Otherwise its
    vanilla parent chain is read from the reference templates: the first
    elements found on the way up are the model's, textures merge with the
    model's own taking precedence, and ``#name`` texture variables are resolved
    to what they finally point at, so each face names a real texture.

    ``minecraft`` is the game version the mod declares: a template whose boxes
    changed between versions (``portkit.data.models.SINCE``) is only used for
    a mod declaring the version it matches or later.
    """
    if model.get("elements"):
        return model, ""
    parent = model.get("parent")
    if not isinstance(parent, str):
        return None, "model has no parent and no elements"
    from ..data import FETCH_COMMAND
    from ..data.models import SINCE, templates
    from ..data.tags import version_key

    known = templates()
    if known is None:
        return None, (
            f"model extends {parent!r}, whose boxes are in vanilla's model, and the "
            f"vanilla model templates aren't cached (run `{FETCH_COMMAND}`)"
        )
    if parent not in known:
        return None, f"model parent {parent!r} is not one of the vanilla templates portkit reads"

    textures = dict(model.get("textures") or {})
    elements = None
    current: str | None = parent
    for _ in range(_MAX_PARENT_DEPTH):
        if current is None:
            break
        body = known.get(current)
        if not isinstance(body, dict):
            return None, f"vanilla template {current!r} is missing from the reference data"
        for key, value in (body.get("textures") or {}).items():
            textures.setdefault(key, value)
        if elements is None and body.get("elements"):
            elements = body["elements"]
            since = SINCE.get(current)
            if since is not None:
                declared = version_key(minecraft)
                if declared is None or declared < version_key(since):
                    return None, (
                        f"vanilla template {current!r} changed its boxes in {since}, and this "
                        f"mod declares {('game version ' + str(minecraft)) if minecraft else 'no game version'}; "
                        "portkit reads only the newer model"
                    )
        current = body.get("parent") if isinstance(body.get("parent"), str) else None
    if not elements:
        return None, f"vanilla template {parent!r} has no elements"

    # Java derives a face's uv from the box when the model names none; write it
    # down, so the geometry says it rather than leaving it to Bedrock.
    elements = json.loads(json.dumps(elements))
    for element in elements:
        for face, spec in (element.get("faces") or {}).items():
            if isinstance(spec, dict) and spec.get("uv") is None and face in _FACE_NORMAL:
                try:
                    spec["uv"] = auto_uv(face, element["from"], element["to"])
                except (KeyError, TypeError, ValueError):
                    return None, f"vanilla template {parent!r} has an element without usable from/to"
            if isinstance(spec, dict) and "tintindex" in spec:
                return None, (
                    f"vanilla template {parent!r} tints its {face} face, a colour Java's "
                    "code computes"
                )
        if not _apply_rescale(element):
            return None, f"vanilla template {parent!r} has an unreadable rescaled rotation"

    resolved: dict = {}
    for key, value in textures.items():
        seen = {key}
        while isinstance(value, str) and value.startswith("#") and value[1:] in textures and value[1:] not in seen:
            seen.add(value[1:])
            value = textures[value[1:]]
        resolved[key] = value
    return {**model, "elements": elements, "textures": resolved}, ""


def _apply_rescale(element: dict) -> bool:
    """Fold a rotation's ``rescale`` into the box, in place. False if unreadable.

    Java (FaceBakery.applyElementRotation, rotateVertexBy) rotates each vertex
    about the origin and then multiplies it, relative to the origin, by
    1/cos(angle) on the two axes the rotation turns (22.5 and 45 degrees are the
    only angles it writes). That scale is the same on both axes of the plane the
    rotation turns, so it commutes with the rotation: stretching the box about
    the origin first, then rotating, puts every vertex where Java puts it.
    Bedrock has no rescale, so the stretched box is what the geometry carries.
    Face uvs are untouched, as in Java (they were made explicit above, from the
    unstretched box, before this runs). Used only for vanilla templates
    (vanilla's cross planes); a mod's own rescaled elements are read as before.
    """
    spec = element.get("rotation")
    if not isinstance(spec, dict) or not spec.get("rescale"):
        return True
    try:
        angle = float(spec.get("angle", 0))
        origin = [float(v) for v in spec.get("origin", _CENTRE_ORIGIN)]
        start = [float(v) for v in element["from"]]
        end = [float(v) for v in element["to"]]
    except (KeyError, TypeError, ValueError):
        return False
    axis = _AXIS_INDEX.get(spec.get("axis"))
    if axis is None or len(origin) != 3:
        return False
    factor = 1.0 / math.cos(math.radians(abs(angle)))
    for i in range(3):
        if i == axis:
            continue
        start[i] = round(origin[i] + (start[i] - origin[i]) * factor, 4)
        end[i] = round(origin[i] + (end[i] - origin[i]) * factor, 4)
    element["from"], element["to"] = start, end
    element["rotation"] = {k: v for k, v in spec.items() if k != "rescale"}
    return True


def turn_locked(element: dict, x_degrees: int, y_degrees: int) -> tuple[dict | None, str]:
    """An element as a Java blockstate x/y turn WITH uvlock leaves it, or why not.

    uvlock keeps every face's texture fixed to the world while the box moves.
    That is exactly the uv Java derives from a face's position (see auto_uv),
    so the case taken is the one we can state: an unrotated element whose faces
    carry position-derived uvs (or none) and no texture rotation. The box moves
    as turn_rigid moves it, each face lands where its normal now points, and
    wears the position-derived uv of where it landed.
    """
    if not (x_degrees % 360 or y_degrees % 360):
        return element, ""
    if element.get("rotation"):
        return None, "blockstate turns a model whose elements are themselves rotated"
    try:
        start = [float(c) for c in element["from"]]
        end = [float(c) for c in element["to"]]
    except (KeyError, TypeError, ValueError):
        return None, "element is missing usable from/to coordinates"
    if element.get(NEGATIVE_MARK):
        return None, _NEGATIVE_UVLOCK
    for face, spec in (element.get("faces") or {}).items():
        if not isinstance(spec, dict):
            continue
        corners = spec.get("uv")
        if corners is not None:
            try:
                same = [float(v) for v in corners] == auto_uv(face, start, end)
            except (TypeError, ValueError, KeyError):
                same = False
            if not same:
                return None, (
                    f"blockstate turns a model with a hand-set uv on its {face} face, and "
                    "uvlock would replace it in a way that is not mapped yet"
                )
        if spec.get("rotation"):
            return None, (
                f"blockstate turns a model whose {face} face turns its texture, and uvlock "
                "would undo that in a way that is not mapped yet"
            )
    moved, why = turn_rigid(element, x_degrees, y_degrees)
    if moved is None:
        return None, why
    faces = {}
    for face, spec in (moved.get("faces") or {}).items():
        spec = {k: v for k, v in spec.items() if k != "rotation"}
        spec["uv"] = auto_uv(face, moved["from"], moved["to"])
        faces[face] = spec
    return {**moved, "faces": faces}, ""


def bounding_boxes(elements: list) -> tuple[list[dict] | None, str]:
    """Bedrock collision boxes for unrotated elements, in the same mirrored
    space cube() puts the geometry in."""
    boxes = []
    for element in elements:
        if element.get("rotation"):
            return None, "a rotated element has no box-shaped collision"
        try:
            x1, y1, z1 = (float(v) for v in element["from"])
            x2, y2, z2 = (float(v) for v in element["to"])
        except (KeyError, TypeError, ValueError):
            return None, "element is missing usable from/to coordinates"
        origin_x = _HALF - x2 if X_AXIS_IS_FLIPPED else x1 - _HALF
        boxes.append({"origin": [origin_x, y1, z1 - _HALF], "size": [x2 - x1, y2 - y1, z2 - z1]})
    return boxes, ""
