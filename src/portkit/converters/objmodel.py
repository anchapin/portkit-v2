"""NeoForge/Forge OBJ block models read as Java elements (#296).

A model whose ``loader`` is ``neoforge:obj`` (NeoForge 1.20.2+) or
``forge:obj`` (Forge 1.19+) builds its quads from a Wavefront ``.obj`` file
and its ``.mtl`` material library instead of JSON ``elements``. This reads
that file the way NeoForge's loader does and, where every visible piece of
the mesh is an axis-aligned box, gives the model back as ordinary Java
elements, so every reader downstream (variants, turns, held states, Bedrock
cubes) treats it as any JSON model.

Source read: neoforged/NeoForge branch 1.21.1 (624c929),
``src/main/java/net/neoforged/neoforge/client/model/obj/``:

- ``ObjLoader#read``: the keys ``model`` (required), ``automatic_culling``
  (default true), ``shade_quads`` (true), ``flip_v`` (false),
  ``emissive_ambient`` (true) and ``mtl_override`` (none).
- ``ObjTokenizer#readAndSplitLine`` L32-66: a line starting ``#`` is a
  comment, a trailing ``\\`` joins the next line, tokens split on spaces and
  tabs.
- ``ObjModel#parse`` L91-258: ``mtllib`` (relative to the model's folder, or
  a full ``namespace:path``; ignored under ``mtl_override``), ``usemtl``,
  ``v`` (x y z [w], divided by w), ``vt``, ``vn``, ``vc``, ``f`` (1-based
  or negative indices ``v/vt/vn/vc``), ``g`` and ``o`` (parts: ``o`` above
  ``g`` makes ``g`` a child object named ``group/name``).
- ``ObjModel#makeQuad`` L315-434: a face is baked as one quad from its first
  four vertices (a triangle repeats its last); positions are in block units
  (0-1); ``vt`` maps across the material's sprite, with ``v`` flipped under
  ``flip_v``; a vertex with no ``vt`` takes (0,0),(0,1),(1,1),(1,0) by
  position in the face; the normal is the ``vn`` given, else
  (v1-v0) x (v2-v0); ``emissive_ambient`` turns the material's ``Ka`` into
  baked light; ``automatic_culling`` culls a face lying on the block's
  boundary plane whose normal points out of it; ``shade_quads`` false bakes
  unshaded quads.
- ``ModelMesh#addQuads`` L541-557: a mesh with no material draws nothing;
  ``Kd`` tints and ``neoforge_TintIndex``/``forge_TintIndex`` sets the tint
  index; ``map_Kd`` names the texture, ``#name`` read from the model's
  ``textures`` (``UnbakedGeometryHelper#resolveDirtyMaterial``).
- ``ObjModel#addQuads`` L295-299 and ``ModelGroup#addQuads`` L494-499: a
  part is drawn unless the model's ``visibility`` sets its name false.
- ``ObjMaterialLibrary`` L28-87: ``newmtl``, ``Ka``, ``Kd``, ``map_Kd`` (last
  token), ``neoforge_TintIndex``/``forge_TintIndex``; a ``usemtl`` naming no
  material fails the model (``getMaterial`` throws).

Bedrock block geometry is drawn from boxes. Bedrock's ``poly_mesh`` (a
triangle or quad mesh in a bone) is marked experimental in the geometry
1.12.0 schema and deprecated from 1.14.0, and Minecraft Creator Tools'
validator fails any geometry that carries one (GEOFMT101 "Restricted Poly
Mesh", learn.microsoft.com/minecraft/creator/reference/content/
mctoolsvalreference/geofmt), so no mesh is written as one. A piece of the
mesh (faces joined by shared corners, inside one part) becomes one element
only when it is exactly a box: every face a quad lying on a side of the
piece's bounds and covering it corner to corner, wound outwards, one per
side, with texture coordinates a Java face can carry (``uv`` and a quarter
``rotation``). Anything else is a reason, never an approximation (#87).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from portkit.converters import models
from portkit.model import SourceMod

OBJ_LOADERS = ("neoforge:obj", "forge:obj")

# ObjLoader#read's keys, plus the plain model keys a loader model still has.
_OBJ_KEYS = {"model", "automatic_culling", "shade_quads", "flip_v", "emissive_ambient", "mtl_override"}
_MODEL_KEYS = {"loader", "parent", "textures", "display", "gui_light", "ambientocclusion",
               "render_type", "visibility", "credit"}

_DEFAULT_COORDS = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))
_EPS = 1e-5  # Mth.equal

_NEGATIVE = {0: "west", 1: "down", 2: "north"}
_POSITIVE = {0: "east", 1: "up", 2: "south"}
_AXIS_OF = {"west": 0, "east": 0, "down": 1, "up": 1, "north": 2, "south": 2}

WHY_NO_MESH = ("Bedrock block geometry is boxes (a poly_mesh is a restricted feature Minecraft "
               "Creator Tools fails, GEOFMT101), so the mesh isn't drawn")


@dataclass(eq=False)
class _Material:
    name: str
    ambient: tuple = (0.0, 0.0, 0.0, 0.0)
    diffuse: tuple = (1.0, 1.0, 1.0, 1.0)
    texture: str | None = None
    tint: int = -1


@dataclass
class _Part:
    name: str
    faces: list = field(default_factory=list)  # (material, [(v, vt, vn, vc)])
    children: list = field(default_factory=list)


def _lines(text: str):
    """ObjTokenizer#readAndSplitLine."""
    rows = text.splitlines()
    i = 0
    while i < len(rows):
        line = rows[i]
        i += 1
        if line.startswith("#"):
            continue
        parts: list[str] = []
        while True:
            more = line.endswith("\\")
            parts += [p for p in (line[:-1] if more else line).replace("\t", " ").split(" ") if p]
            if not more or i >= len(rows):
                break
            line = rows[i]
            if not line or line.startswith("#"):
                break
            i += 1
        if parts:
            yield parts


def _vec(tokens: list[str], size: int) -> tuple:
    """ObjModel#parseVector2/3/4: missing values are 0, a missing w is 1."""
    values = [float(t) for t in tokens[1:size + 1]]
    if size == 4 and len(tokens) == 1:
        return (0.0, 0.0, 0.0, 0.0)
    out = values + [0.0] * (size - len(values))
    if size == 4 and len(values) < 4:
        out[3] = 1.0
    return tuple(out)


def _resource(mod: SourceMod, name: str, folder: str) -> tuple[Path | None, str]:
    """A ``namespace:path`` (or a path relative to ``folder``) inside the mod."""
    if ":" in name:
        namespace, rel = name.split(":", 1)
    else:
        namespace, rel = mod.namespace, folder + name
    if namespace != mod.namespace:
        return None, f"{name!r} is another namespace's"
    path = mod.assets.parent / namespace / rel
    if not path.is_file():
        return None, f"{name!r} is not in this mod"
    return path, ""


def _read_mtl(path: Path) -> tuple[dict | None, str]:
    materials: dict[str, _Material] = {}
    current = None
    try:
        for line in _lines(path.read_text(encoding="utf-8")):
            key = line[0]
            if key == "newmtl":
                current = materials[" ".join(line[1:])] = _Material(" ".join(line[1:]))
            elif current is None and key in ("Ka", "Kd", "map_Kd", "forge_TintIndex", "neoforge_TintIndex"):
                return None, f"{path.name} sets {key} before any newmtl (Java fails the library)"
            elif key == "Ka":
                current.ambient = _vec(line, 4)
            elif key == "Kd":
                current.diffuse = _vec(line, 4)
            elif key == "map_Kd":
                current.texture = line[-1]
            elif key in ("forge_TintIndex", "neoforge_TintIndex"):
                current.tint = int(line[1])
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        return None, f"{path.name} can't be read ({exc})"
    return materials, ""


def _parse(mod: SourceMod, obj: Path, folder: str, mtl_override: str | None, files: list):
    """ObjModel#parse: the parts in file order, and the vertex lists."""
    pos: list = []
    tex: list = []
    nor: list = []
    col: list = []
    parts: dict[str, _Part] = {}
    mtllib: dict = {}
    if mtl_override is not None:
        path, why = _resource(mod, mtl_override, folder)
        if path is None:
            return None, f"its mtl_override {why}"
        files.append(path)
        mtllib, why = _read_mtl(path)
        if mtllib is None:
            return None, why
    mat = None
    group = None
    target = None  # the part (group or child object) faces go to
    obj_above = False
    try:
        for line in _lines(obj.read_text(encoding="utf-8")):
            key = line[0]
            if key == "mtllib" and mtl_override is None:
                path, why = _resource(mod, line[1], folder)
                if path is None:
                    return None, f"its material library {why}"
                files.append(path)
                mtllib, why = _read_mtl(path)
                if mtllib is None:
                    return None, why
            elif key == "usemtl":
                name = " ".join(line[1:])
                if name not in mtllib:
                    return None, f"usemtl {name!r} names no material in its library (Java fails the model)"
                mat = mtllib[name]
            elif key == "v":
                x, y, z, w = _vec(line, 4)
                pos.append((x / w, y / w, z / w))
            elif key == "vt":
                tex.append(_vec(line, 2))
            elif key == "vn":
                nor.append(_vec(line, 3))
            elif key == "vc":
                col.append(_vec(line, 4))
            elif key == "f":
                if target is None:
                    group = target = parts.setdefault("", _Part(""))
                face = []
                for token in line[1:]:
                    idx = [int(n) if n else 0 for n in token.split("/")]
                    for k, size in enumerate((len(pos), len(tex), len(nor), len(col))[:len(idx)]):
                        idx[k] = size + idx[k] if idx[k] < 0 else idx[k] - 1
                    if not 0 <= idx[0] < len(pos):
                        return None, f"{obj.name} has a face naming a vertex it doesn't have"
                    face.append(tuple(idx))
                target.faces.append((mat, face))
            elif key == "g":
                if obj_above:
                    target = _Part(f"{group.name}/{line[1]}")
                    group.children.append(target)
                else:
                    group = target = _Part(line[1])
                    parts[line[1]] = group
            elif key == "o":
                if obj_above or group is None:
                    obj_above = True
                    group = target = _Part(line[1])
                    parts[line[1]] = group
                else:
                    target = _Part(f"{group.name}/{line[1]}")
                    group.children.append(target)
    except (ValueError, IndexError, UnicodeDecodeError, ZeroDivisionError) as exc:
        return None, f"{obj.name} can't be read ({exc})"
    return (list(parts.values()), pos, tex, nor, col), ""


def _pieces(faces: list, pos: list) -> list[list]:
    """Faces joined by shared corner positions, in file order."""
    parent: dict = {}

    def find(p):
        while parent.setdefault(p, p) != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    for _, verts in faces:
        first = find(pos[verts[0][0]])
        for v in verts[1:]:
            parent[find(pos[v[0]])] = first
    pieces: dict = {}
    for face in faces:
        pieces.setdefault(find(pos[face[1][0][0]]), []).append(face)
    return list(pieces.values())


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _nearest(n) -> str | None:
    """The face a normal points out of (None for a zero vector)."""
    best, score = None, 0.0
    for face, normal in models._FACE_NORMAL.items():
        d = sum(n[i] * normal[i] for i in range(3))
        if d > score:
            best, score = face, d
    return best


def _tidy(value: float):
    value = round(value, 5)
    return int(value) if value == int(value) else value


def _slot(material: str) -> str:
    """The texture slot a material's own texture location is put in."""
    return "obj_" + "".join(c if c.isalnum() else "_" for c in material)


def _face_uv(face: str, start: list, end: list, quad: list) -> dict | None:
    """The uv and rotation Java bakes onto these four (corner, uv), if any
    (models.baked_quad: FaceBakery, FaceInfo, BlockFaceUV)."""
    by_corner = {p: uv for p, uv in quad}
    for rotation in (0, 90, 180, 270):
        shift = rotation // 90
        picks = {}
        for i, pick in enumerate(models._FACE_INFO[face]):
            point = tuple(float(end[a] if h else start[a]) for a, h in enumerate(pick))
            picks[(i + shift) % 4] = by_corner.get(point)
        if picks.get(0) is None or picks.get(2) is None:
            return None
        uv = [picks[0][0], picks[0][1], picks[2][0], picks[2][1]]
        if models._same_quad(models.baked_quad(face, start, end, uv, rotation), quad):
            return {"uv": uv, **({"rotation": rotation} if rotation else {})}
    return None


def _box(piece: list, pos, tex, nor, flip_v: bool, cull: bool) -> tuple[dict | None, str]:
    """One piece as a Java element, or why it isn't exactly a box."""
    corners = {pos[v[0]] for _, verts in piece for v in verts}
    lo = [min(p[a] for p in corners) for a in range(3)]
    hi = [max(p[a] for p in corners) for a in range(3)]
    start = [_tidy(lo[a] * 16) for a in range(3)]
    end = [_tidy(hi[a] * 16) for a in range(3)]
    faces: dict[str, dict] = {}
    for mat, verts in piece:
        if len(verts) != 4:
            return None, (f"a face has {len(verts)} corners (Java bakes a face as one quad, and a box "
                          "side is one quad)")
        if any(len(v) >= 4 for v in verts):
            return None, "a face sets vertex colours (vc), which a Java element face can't carry"
        ps = [pos[v[0]] for v in verts]
        if len(set(ps)) != 4:
            return None, "a face repeats a corner"
        planes = [a for a in range(3) if len({p[a] for p in ps}) == 1]
        if len(planes) != 1:
            return None, "a face doesn't lie flat across one axis (not axis-aligned)"
        axis = planes[0]
        value = ps[0][axis]
        o1, o2 = [b for b in range(3) if b != axis]
        rect = {(x, y) for x in (lo[o1], hi[o1]) for y in (lo[o2], hi[o2])}
        if {(p[o1], p[o2]) for p in ps} != rect or value not in (lo[axis], hi[axis]):
            return None, "a face lies inside the piece's bounds instead of covering one side corner to corner"
        computed = _cross(_sub(ps[1], ps[0]), _sub(ps[2], ps[0]))
        wound = _nearest(computed)
        given = all(len(v) >= 3 for v in verts) and nor
        if given and not 0 <= verts[0][2] < len(nor):
            return None, "a face names a normal the file doesn't have"
        side = _nearest(nor[verts[0][2]]) if given else wound
        outward = (_NEGATIVE[axis] if value == lo[axis] and lo[axis] != hi[axis] else
                   _POSITIVE[axis] if value == hi[axis] and lo[axis] != hi[axis] else None)
        if wound is None or wound != side or _AXIS_OF[wound] != axis or (outward and wound != outward):
            return None, "a face is wound or lit inwards (Java shows it from inside the box)"
        if wound in faces:
            return None, f"two faces lie on its {wound} side"
        if mat is None:
            faces[wound] = None  # ModelMesh#addQuads: no material, nothing drawn
            continue
        if mat.texture is None:
            return None, f"material {mat.name!r} names no texture (map_Kd)"
        if any(abs(c - 1.0) > _EPS for c in mat.diffuse):
            return None, f"material {mat.name!r} tints its faces (Kd {list(mat.diffuse)})"
        uvs = []
        for i, v in enumerate(verts):
            if len(v) >= 2 and tex:
                if not 0 <= v[1] < len(tex):
                    return None, "a face names a texture coordinate the file doesn't have"
                u, w = tex[v[1]]
            else:
                u, w = _DEFAULT_COORDS[i]
            uvs.append((_tidy(u * 16), _tidy((1 - w if flip_v else w) * 16)))
        quad = [(tuple(float(_tidy(c * 16)) for c in p), uv) for p, uv in zip(ps, uvs)]
        spec = _face_uv(wound, start, end, quad)
        if spec is None:
            return None, (f"its {wound} side's texture coordinates aren't a rectangle a Java face "
                          "can carry (uv and a quarter rotation)")
        spec["texture"] = mat.texture if mat.texture.startswith("#") else f"#{_slot(mat.name)}"
        if mat.tint != -1:
            spec["tintindex"] = mat.tint
        if cull and all(abs(p[axis] - (0.0 if wound == _NEGATIVE[axis] else 1.0)) <= _EPS for p in ps):
            spec["cullface"] = wound
        faces[wound] = spec
    drawn = {k: s for k, s in faces.items() if s is not None}
    if not drawn:
        return {}, ""
    return {"from": start, "to": end, "faces": drawn}, ""


def is_obj(model: object) -> bool:
    return isinstance(model, dict) and model.get("loader") in OBJ_LOADERS


def read(mod: SourceMod, model: dict) -> tuple[dict | None, list[Path], str]:
    """An OBJ loader model as a JSON model with ``elements``: the model
    with its loader keys replaced, the .obj/.mtl files read, and a reason
    when it can't be one."""
    files: list[Path] = []
    loader = model.get("loader")
    source = model.get("model")
    label = source.split("/")[-1] if isinstance(source, str) else "?"
    head = f"OBJ model {label!r} ({loader})"
    unread = sorted(k for k in model if k not in _OBJ_KEYS | _MODEL_KEYS)
    if unread:
        return None, files, f"{head} sets {', '.join(unread)}, which the OBJ reader doesn't read"
    if not isinstance(source, str):
        return None, files, f"{head} names no .obj file"
    flags = {}
    for key, default in (("automatic_culling", True), ("shade_quads", True), ("flip_v", False),
                         ("emissive_ambient", True)):
        value = model.get(key, default)
        if not isinstance(value, bool):
            return None, files, f"{head} sets {key} to {value!r}, not true or false"
        flags[key] = value
    override = model.get("mtl_override")
    if override is not None and not isinstance(override, str):
        return None, files, f"{head} sets an unreadable mtl_override"
    visibility = model.get("visibility") or {}
    if not isinstance(visibility, dict):
        return None, files, f"{head} sets an unreadable visibility"
    path, why = _resource(mod, source, "")
    if path is None:
        return None, files, f"{head}: the .obj file {why}"
    files.append(path)
    rel = source.split(":", 1)[-1]
    folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
    parsed, why = _parse(mod, path, folder, override, files)
    if parsed is None:
        return None, files, f"{head}: {why}"
    parts, pos, tex, nor, _col = parsed
    elements: list[dict] = []
    materials: list = []
    for part in parts:
        if visibility.get(part.name, True) is False:
            continue
        for sub in [part] + [c for c in part.children if visibility.get(c.name, True) is not False]:
            pieces = _pieces(sub.faces, pos)
            for n, piece in enumerate(pieces, 1):
                if flags["emissive_ambient"] and any(
                        m is not None and int((m.ambient[0] + m.ambient[1] + m.ambient[2]) * 15 / 3.0) != 0
                        for m, _ in piece):
                    return None, files, (f"{head} part {sub.name!r}: its material's Ka bakes light into the "
                                         "faces (emissive_ambient), which a Bedrock box can't carry")
                element, why = _box(piece, pos, tex, nor, flags["flip_v"], flags["automatic_culling"])
                if element is None:
                    return None, files, (f"{head} part {sub.name!r} piece {n} of {len(pieces)} is not an "
                                         f"axis-aligned box: {why}; {WHY_NO_MESH}")
                if element:
                    for m, _ in piece:
                        if m is not None and m not in materials:
                            materials.append(m)
                    if not flags["shade_quads"]:
                        element["shade"] = False
                    elements.append(element)
    if not elements:
        return None, files, f"{head} draws no face"
    out = {k: v for k, v in model.items() if k in _MODEL_KEYS and k not in ("loader", "visibility")}
    textures = dict(out.get("textures") or {})
    for material in materials:
        if material.texture is not None and not material.texture.startswith("#"):
            slot = _slot(material.name)
            if textures.get(slot, models.normalize(material.texture)) != models.normalize(material.texture):
                return None, files, f"{head}: the model already has a texture named {slot!r}"
            # UnbakedGeometryHelper#resolveDirtyMaterial: a location, vanilla's
            # namespace when it names none.
            textures[slot] = models.normalize(material.texture)
    out["textures"] = textures
    out["elements"] = elements
    return out, files, ""
