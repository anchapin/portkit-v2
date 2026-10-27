"""Immersive Engineering's own OBJ model loader, ``immersiveengineering:ie_obj`` (#296).

Source read: BluSunrize/ImmersiveEngineering tag ``12.4.2-194``
(``src/main/java/blusunrize/immersiveengineering/client/models/obj/``), and
the OBJ parser it bundles, malte0811/BlockModelSplitter (jar-in-jar
``META-INF/jarjar/BlockModelSplitter-2.0.1.jar``; source read at fa199b7,
``model/OBJModel.java``, ``model/MaterialLibrary.java``):

* ``IEOBJLoader#read`` (L42-70): the keys ``model`` (required), ``callbacks``
  (a registered ``IEOBJCallback``; ``DefaultCallback`` when absent),
  ``dynamic`` and ``layers`` (render types; solid when absent). The file is
  read by ``OBJModel#readFromStream``, then ``quadify()`` and
  ``recomputeZeroNormals()``.
* ``OBJModel#readFromStream``: lines that are empty or start with ``#`` are
  skipped and the rest split on whitespace; ``mtllib`` (relative to the
  model's folder unless it names a namespace), ``v`` (x y z), ``vn``, ``vt``
  (u v), ``f`` (``v/vt[/vn]``, 1-based; a missing ``vt`` is (0, 0) and a
  missing ``vn`` a zero normal, recomputed), ``o`` (the group faces go to,
  ``default`` before any; a repeated name is the same group), ``usemtl``; any
  other line (``g``, ``s``, ...) is ignored. ``MaterialLibrary#parse`` reads
  only ``newmtl`` and ``map_Kd`` (a material without one fails the model).
* ``SpecificIEOBJModel#addQuadsForGroup`` / ``#addGroupQuads`` (L190-266) and
  ``client/models/split/PolygonUtils#toBakedQuad``: a group is drawn when the
  callback's ``getIEOBJState(key).visibility()`` shows it and
  ``shouldRenderGroup`` is true; a face with no material draws nothing; its
  texture is the callback's ``getTextureReplacement`` or the material's
  ``map_Kd`` (``#name`` from the model's textures); its colour the callback's
  ``getRenderColor`` (white unless overridden: ``Ka``/``Kd`` aren't read);
  uv ``(u, 1 - v)`` across the sprite unless ``useAbsoluteUV``; shaded unless
  ``shadeQuads`` says not; transformed by ``applyTransformations``; then
  ``modifyQuads``. ``getQuads`` answers only for no side, so no face is culled.
* ``GeneralIEOBJModel#getModelData`` / ``#getKey``: the key is the callback's
  ``extractKey(level, pos, state, blockEntity)`` in the world, its
  ``getDefaultKey()`` where the model data has none.
* ``ClientProxy#modConstruction``: ``IEOBJCallbacks.register(ImmersiveEngineering.rl(name),
  Foo.INSTANCE)`` per callback.

:func:`read` reads the JSON and the mesh that way and hands the drawn groups
to the generic reader (:func:`portkit.converters.objmodel.as_model`), whose
rule is the same as for NeoForge's loader: a piece becomes an element only
when it is exactly a box (#395). A callback whose only drawing method is
``getIEOBJState`` (it only picks the groups drawn, as ``ChuteCallbacks``
does) is run, with the key ``extractKey`` reads from the block's block entity
as placed with nothing beside it (pick 1a, approved by Alex 2026-10-26; see
:func:`_placed_alone`). A callback that overrides any other method that
decides what is drawn is read from the jar (its class and the methods it
declares) and named; it isn't run, so its model is a reason, never a guess.
"""
from __future__ import annotations

from portkit.converters import objmodel

LOADER = "immersiveengineering:ie_obj"
_NAMESPACE = "immersiveengineering"
_KEYS = {"model", "callbacks", "dynamic", "layers"}
_REGISTER = ("blusunrize/immersiveengineering/api/client/ieobj/IEOBJCallbacks", "register")
_RL = ("blusunrize/immersiveengineering/ImmersiveEngineering", "rl", "(Ljava/lang/String;)Lnet/minecraft/resources/ResourceLocation;")
_DEFAULT = "blusunrize/immersiveengineering/api/client/ieobj/DefaultCallback"
# IEOBJCallback / BlockCallback methods whose answer changes what a block's
# model draws (IEOBJCallback.java, BlockCallback.java, tag 12.4.2-194);
# extractKey/getDefaultKey only give the key the others are asked with.
_DRAWING = ("getIEOBJState", "shouldRenderGroup", "dependsOnLayer", "getTextureReplacement",
            "getRenderColor", "useAbsoluteUV", "shadeQuads", "applyTransformations", "modifyQuads")


def _short(name: str) -> str:
    return name.rsplit("/", 1)[-1]


_FOUND: dict = {}  # id(class index) -> (the index, its registrations)


def _registered(classes) -> dict[str, str]:
    """``immersiveengineering:<name>`` -> callback class (slashed), from
    every ``IEOBJCallbacks.register(ImmersiveEngineering.rl("<name>"),
    Foo.INSTANCE)`` in the jar's code (read once per class index)."""
    held = _FOUND.get(id(classes))
    if held is not None and held[0] is classes:
        return held[1]
    found = _read_registered(classes)
    _FOUND.clear()
    _FOUND[id(classes)] = (classes, found)
    return found


def _read_registered(classes) -> dict[str, str]:
    from portkit.bytecode import Ref, instructions
    found: dict[str, str] = {}
    for cname in classes.names():
        raw = classes.raw(cname)
        if raw is None or b"IEOBJCallbacks" not in raw:
            continue
        cf = classes.get(cname)
        if cf is None:
            continue
        for m in cf.methods:
            if not m.code:
                continue
            ins = instructions(cf, m.code)
            for i, x in enumerate(ins):
                if not (isinstance(x.arg, Ref) and (x.arg.owner, x.arg.name) == _REGISTER) or i < 3:
                    continue
                ldc, rl, inst = ins[i - 3], ins[i - 2], ins[i - 1]
                if ldc.name.startswith("ldc") and isinstance(ldc.arg, str) and isinstance(rl.arg, Ref) \
                        and (rl.arg.owner, rl.arg.name, rl.arg.desc) == _RL and inst.name == "getstatic" \
                        and isinstance(inst.arg, Ref) and inst.arg.name == "INSTANCE":
                    found.setdefault(f"{_NAMESPACE}:{ldc.arg}", inst.arg.owner)
    return found


def _overrides(classes, cls: str) -> list[str]:
    """The drawing methods (``_DRAWING``) the callback class or a mod
    superclass of it declares with code, in ``_DRAWING`` order."""
    names: set[str] = set()
    seen: set[str] = set()
    while cls and cls not in seen and cls != "java/lang/Object":
        seen.add(cls)
        cf = classes.get(cls)
        if cf is None:
            break
        names |= {m.name for m in cf.methods if m.code is not None}
        cls = cf.super_name
    return [n for n in _DRAWING if n in names]


_BLOCK_CALLBACK_KEY = ("extractKey", "(Lnet/minecraft/world/level/BlockAndTintGetter;Lnet/minecraft/core/BlockPos;"
                       "Lnet/minecraft/world/level/block/state/BlockState;"
                       "Lnet/minecraft/world/level/block/entity/BlockEntity;)Ljava/lang/Object;")
_API = "blusunrize/immersiveengineering/api/"
_OBJ_STATE = _API + "IEProperties$IEObjState"
_VISIBILITY = _API + "IEProperties$VisibilityList"
_GET_STATE = ("getIEOBJState", f"(Ljava/lang/Object;)L{_OBJ_STATE};")
_NEW_BE = ("newBlockEntity", "(Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;)"
           "Lnet/minecraft/world/level/block/entity/BlockEntity;")
_IDENTITY = ("com/mojang/math/Transformation", "IDENTITY")
_ALONE: dict = {}  # (id(class index), blockstate name, callback, groups) -> (index, answer)


def _placed_alone(mod, classes, cb: str, names: list[str]) -> tuple[dict | None, str]:
    """({group: shown}, "") for the block being converted
    (``models.BLOCK_DRAWN``) under callback class ``cb``, or (None, why).

    ``GeneralIEOBJModel#getModelData`` keys the model with ``cb``'s
    ``extractKey(level, pos, state, blockEntity)``; here that runs on the
    block's block entity as it stands once placed with nothing beside it
    (:func:`portkit.blockcode.read_key_alone`), then ``getIEOBJState`` on
    the key, and each group is drawn when the state's
    ``visibility().isVisible(group)`` (``SpecificIEOBJModel#addQuadsForGroup``)
    is true. Its ``transform()`` must be ``Transformation.identity()``. The
    block entity is the one the block's ``IEEntityBlock#newBlockEntity``
    makes: the type the code that made the block reads, as the facing
    reader finds it (``_type_field`` / ``_entity_of``). Every way the run
    takes (the block state isn't known) must show the same groups."""
    from portkit.converters import models
    drawn = models.BLOCK_DRAWN.get()
    if drawn is None:
        return None, "no placed block is being drawn"
    block, shared = drawn
    key = (id(classes), block, cb, tuple(names))
    held = _ALONE.get(key)
    if held is not None and held[0] is classes:
        return held[1]
    got = _read_alone(classes, block, shared, cb, names)
    if len(_ALONE) > 4096 or any(v[0] is not classes for v in _ALONE.values()):
        _ALONE.clear()
    _ALONE[key] = (classes, got)
    return got


_ENTITY_MEMO: list = [None, {}]  # [class index, _entity_of memo for it]


def _entity_memo(classes) -> dict:
    if _ENTITY_MEMO[0] is not classes:
        _ENTITY_MEMO[:] = [classes, {}]
    return _ENTITY_MEMO[1]


def _read_alone(classes, block: str, shared, cb: str, names: list[str]) -> tuple[dict | None, str]:
    from portkit import blockcode
    from . import _ENTITY_BLOCK, _chain, _declaring, _entity_of, _type_field
    run = shared() if callable(shared) else shared
    if run is None or block not in run[1]:
        return None, f"the block {block} isn't found registered"
    objs, why = run[1][block]
    if not objs:
        return None, f"the block {block}: {why}"
    if len({o.cls for o in objs}) != 1 or len({getattr(o, "_made_in", None) for o in objs}) != 1:
        return None, f"the block {block} is registered as more than one block"
    cls, site = objs[0].cls, getattr(objs[0], "_made_in", None)
    if _ENTITY_BLOCK not in _chain(classes, cls):
        return None, f"{cls.replace('/', '.')} isn't an IEEntityBlock, so its block entity isn't read"
    cf, _m = _declaring(classes, cls, *_NEW_BE)
    if cf is None or cf.name != _ENTITY_BLOCK:
        return None, f"{cls.replace('/', '.')}'s newBlockEntity isn't IEEntityBlock's"
    field, why = _type_field(classes, site, cls)
    if field is None:
        return None, why
    be, why = _entity_of(classes, field, _entity_memo(classes))
    if be is None:
        return None, why
    machine = blockcode.Machine(classes)
    states, why = blockcode.read_key_alone(classes, be, cb, _BLOCK_CALLBACK_KEY, _GET_STATE, machine=machine)
    if states is None:
        return None, f"its key from {_short(be)} placed alone isn't read: {why}"
    shown: dict | None = None
    for state in states:
        if not isinstance(state, blockcode.Obj) or state.cls != _OBJ_STATE:
            return None, f"{_short(cb)}#getIEOBJState doesn't give an IEObjState that is read"
        try:
            transform = machine.call(_OBJ_STATE, "transform", "()Lcom/mojang/math/Transformation;", [state])
            vis = machine.call(_OBJ_STATE, "visibility", f"()L{_VISIBILITY};", [state])
            if transform != [blockcode.Const(*_IDENTITY)]:
                return None, f"{_short(cb)}#getIEOBJState turns the model (its transform isn't the identity)"
            if len(vis) != 1 or not isinstance(vis[0], blockcode.Obj) or vis[0].cls != _VISIBILITY:
                return None, f"{_short(cb)}#getIEOBJState doesn't give one VisibilityList that is read"
            these = {}
            for n in names:
                verdict = machine.call(_VISIBILITY, "isVisible", "(Ljava/lang/String;)Z", [vis[0], n])
                if verdict not in ([0], [1]):
                    return None, f"whether {_short(cb)} shows the group {n!r} isn't read"
                these[n] = bool(verdict[0])
        except blockcode.Unreadable as exc:
            return None, f"{_short(cb)}'s IEObjState can't be read ({exc})"
        if shown is not None and these != shown:
            return None, f"what {_short(cb)} shows depends on the block's state, which isn't known"
        shown = these
    return shown, ""


def _tokens(text: str):
    """OBJModel#getRelevantLines: (key, tokens) per line that isn't empty or
    a comment."""
    for line in text.splitlines():
        if not line.strip() or line[0] == "#":
            continue
        parts = line.split()
        yield parts[0], parts[1:]


def _mtl(path) -> tuple[dict | None, str]:
    """MaterialLibrary#parse: newmtl and map_Kd only."""
    out: dict = {}
    name = kd = None
    for key, rest in _tokens(path.read_text(encoding="utf-8")):
        if key == "newmtl":
            if name is not None:
                if kd is None:
                    return None, f"{path.name}: material {name!r} has no map_Kd (Java fails the model)"
                out[name] = objmodel._Material(name, texture=kd)
            name, kd = rest[0], None
        elif key == "map_Kd":
            kd = rest[0]
    if name is not None:
        if kd is None:
            return None, f"{path.name}: material {name!r} has no map_Kd (Java fails the model)"
        out[name] = objmodel._Material(name, texture=kd)
    return out, ""


def _mesh(mod, source: str, files: list):
    """OBJModel#readFromStream: (groups in first-seen order, positions, uvs,
    normals) or (None, why)."""
    path, why = objmodel._resource(mod, source, "")
    if path is None:
        return None, f"the .obj file {why}"
    files.append(path)
    rel = source.split(":", 1)[-1]
    folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
    pos: list = []
    tex: list = [(0.0, 0.0)]  # UVCoords.ZERO, for a vertex with no vt
    nor: list = []
    groups: dict[str, objmodel._Part] = {}
    current = "default"
    materials: dict | None = None
    mat = None
    try:
        for key, rest in _tokens(path.read_text(encoding="utf-8")):
            if key == "mtllib":
                lib, why = objmodel._resource(mod, rest[0], folder)
                if lib is None:
                    return None, f"its material library {why}"
                files.append(lib)
                materials, why = _mtl(lib)
                if materials is None:
                    return None, why
            elif key == "v":
                pos.append(tuple(float(t) for t in rest[:3]))
            elif key == "vn":
                nor.append(tuple(float(t) for t in rest[:3]))
            elif key == "vt":
                tex.append(tuple(float(t) for t in rest[:2]))
            elif key == "o":
                current = rest[0]
            elif key == "usemtl":
                if materials is None or rest[0] not in materials:
                    return None, f"usemtl {rest[0]!r} names no material (Java fails the model)"
                mat = materials[rest[0]]
            elif key == "f":
                face = []
                for token in rest:
                    bits = token.split("/")
                    p = int(bits[0]) - 1
                    t = int(bits[1]) if bits[1] else 0  # index 0 is (0, 0)
                    if not 0 <= p < len(pos) or not 0 <= t < len(tex):
                        return None, f"{path.name} has a face naming a vertex it doesn't have (Java fails the model)"
                    if len(bits) > 2 and bits[2]:
                        n = int(bits[2]) - 1
                        if not 0 <= n < len(nor):
                            return None, f"{path.name} has a face naming a normal it doesn't have (Java fails the model)"
                        face.append((p, t, n))
                    else:
                        face.append((p, t))  # a zero normal, recomputed from the corners
                groups.setdefault(current, objmodel._Part(current)).faces.append((mat, face))
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        return None, f"{path.name} can't be read ({exc}; Java fails the model)"
    return (list(groups.values()), pos, tex, nor), ""


def read(mod, model: dict) -> tuple[dict | None, list, str]:
    """An ``ie_obj`` model as a JSON model with ``elements``, the files read,
    and the reason when it can't be one."""
    files: list = []
    source = model.get("model")
    label = source.split("/")[-1] if isinstance(source, str) else "?"
    head = f"IE OBJ model {label!r} ({LOADER})"
    unread = sorted(k for k in model if k not in _KEYS | objmodel._MODEL_KEYS)
    if unread:
        return None, files, f"{head} sets {', '.join(unread)}, which the IE OBJ reader doesn't read"
    if not isinstance(source, str):
        return None, files, f"{head} names no .obj file"
    parsed, why = _mesh(mod, source, files)
    if parsed is None:
        return None, files, f"{head}: {why}"
    groups, pos, tex, nor = parsed

    def boxes(shown):
        return objmodel.as_model(model, shown, pos, tex, nor, head=head, flip_v=True, cull=False,
                                 shade=True, ambient_light=False)

    blocker = ""
    name = model.get("callbacks")
    if name is not None:
        classes = getattr(mod, "classes", None)
        cls = _registered(classes).get(name) if classes is not None and isinstance(name, str) else None
        if cls is None:
            blocker = f"its callback {name!r} isn't found registered in the jar (IEOBJCallbacks.register)"
        elif cls != _DEFAULT:
            drawn = _overrides(classes, cls)
            alone_why = ""
            if drawn == ["getIEOBJState"]:
                # Only which groups show is the callback's: read with the
                # key of the block entity as placed with nothing beside it.
                visible, alone_why = _placed_alone(mod, classes, cls, [g.name for g in groups])
                if visible is not None:
                    groups = [g for g in groups if visible[g.name]]
                    drawn = []
            if drawn:
                blocker = (f"its callback {name} ({_short(cls)}) overrides {', '.join(drawn)} "
                           "(IEOBJCallback): Java code IE's model runs, with the key its extractKey "
                           "reads from the placed block, to decide what it draws, which isn't run"
                           + (f" ({alone_why})" if alone_why else ""))
    if not blocker and model.get("dynamic", False) is not False:
        blocker = f"it sets dynamic {model.get('dynamic')!r}, which isn't read"
    if not blocker and model.get("layers") is not None:
        blocker = f"it draws in the render layers {model.get('layers')!r}, which aren't read"
    out, why = boxes(groups)
    if blocker:
        mesh = why[len(head):].lstrip(": ") if out is None and why.startswith(head) else why
        return None, files, f"{head}: {blocker}" + (f"; and its {mesh}" if out is None else "")
    return out, files, why
