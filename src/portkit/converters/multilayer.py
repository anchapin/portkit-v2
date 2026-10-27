"""Layered block models: one block drawn from several models (#296).

Two Java loaders draw a block from sub-models, each in its own render layer:

* **Forge 1.12 ``forge:multi-layer``**, named as a Forge blockstate's
  (``forge_marker`` 1) ``model``; its ``custom`` data maps ``base`` and render
  layer names to model locations. Source: MinecraftForge branch 1.12.x
  (3effde4), ``client/model/MultiLayerModel.java``. ``process`` (L95-115)
  keeps ``base`` and every key equal to a ``BlockRenderLayer#toString``
  (``Solid``, ``Mipped Cutout``, ``Cutout``, ``Translucent``: 1.12.2 client
  jar, class ``amm``'s initializer); ``getLocation`` (L117-126) reads each as
  a ``ModelResourceLocation``. ``MultiLayerBakedModel#getQuads`` (L144-158)
  draws, in each render layer, that layer's model only (the missing model for
  a layer it lacks); ``base`` is drawn only when no layer is set (an item),
  and lends the block its ambient occlusion and particle (L160-189). Which
  layers a block renders in is its code's
  (:func:`portkit.rendershape.read_layers_112`).
* **NeoForge/Forge ``composite``** (``neoforge:composite``,
  ``forge:composite``), a model ``loader``: NeoForge branch 1.21.1 (624c929),
  ``client/model/CompositeModel.java``. ``Loader#read`` (L340-372) reads each
  of ``children`` as a model of its own (its own parents and textures, not the
  composite's); ``bake`` (L68-97) skips a child the composite's
  ``visibility`` hides; ``Baked#getQuads`` (L132-140) draws each child in the
  render types the child's own model names; ambient occlusion is the
  composite's (``context.useAmbientOcclusion``).

Every drawn layer is merged exactly into one model (its elements, its
textures under names that don't collide). Bedrock gives a block one render
method (#262): layers in ``solid`` and ``cutout*`` draw as ``alpha_test`` when
every texture the solid layers wear is the mod's own and has no transparent
pixel (``alpha_test`` then draws those faces the same); ``solid`` beside
``translucent`` draws wholly ``blend`` as a labelled DEFAULT (pick 1a,
:data:`BLEND_DEFAULT`) when every solid face samples only opaque pixels;
anything else (``translucent`` beside a cutout type, an unread solid texture)
is a reason, never a guess. No mod is named here (#220).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .. import png as png_reader
from ..model import SourceMod
from . import models

MULTI_LAYER = "forge:multi-layer"
COMPOSITE_LOADERS = ("neoforge:composite", "forge:composite")

# BlockRenderLayer#toString (1.12) -> the layer.
LAYER_NAMES_112 = {"Solid": "SOLID", "Mipped Cutout": "CUTOUT_MIPPED", "Cutout": "CUTOUT",
                   "Translucent": "TRANSLUCENT"}
# A 1.12 layer -> the NamedRenderTypeManager name for the same chunk layer.
RENDER_TYPE_112 = {"SOLID": "minecraft:solid", "CUTOUT_MIPPED": "minecraft:cutout_mipped",
                   "CUTOUT": "minecraft:cutout", "TRANSLUCENT": "minecraft:translucent"}
_SOLID = "minecraft:solid"
_TRANSLUCENT = "minecraft:translucent"
# DEFAULT (Alex pick 1a, #296, 2026-10-26): a block whose layers are solid
# beside translucent (a translucent shell over a solid core) is drawn wholly
# with Bedrock ``blend``. Bedrock gives a block one render method (#262) and
# no method draws a solid and a translucent layer the same as Java; blend
# draws the translucent layer's partial alpha and, where the solid faces
# sample only opaque pixels, the solid layer's pixels opaque. What differs
# from Java (the solid core sorted in the translucent pass) is a choice, not
# a reading, so it is labelled DEFAULT wherever it is written. This marker is
# the render type such a merged block notes; blocks.py forces every face of
# it to blend.
BLEND_DEFAULT = "portkit:default_blend_translucent_over_solid"
BLEND_DEFAULT_WHY = ("DEFAULT (pick 1a, #296): its layers draw in minecraft:solid and minecraft:translucent; "
                     "Bedrock gives a block one render method (#262), so the whole block draws blend, which "
                     "draws the translucent layer's partial alpha and the solid layer's faces (each samples only "
                     "opaque pixels) opaque, but sorted with the translucent pass")
_CUTOUT = frozenset({"minecraft:cutout", "minecraft:cutout_mipped", "minecraft:cutout_mipped_all"})
# Forge v1 named transforms that set only the held/GUI perspectives
# (ForgeBlockStateV1 L935-971: no TransformType.NONE entry), so the block in
# the world is untouched.
_PERSPECTIVE_ONLY = frozenset({"identity", "forge:default-block"})
# A composite's own parent lends it only display, AO and particle: its own
# geometry replaces any parent elements (BlockGeometryBakingContext
# #getCustomGeometry: the model's own loader first).
_COMPOSITE_KEYS = frozenset({"loader", "parent", "children", "item_render_order", "visibility", "textures",
                             "display", "gui_light", "ambientocclusion", "render_type", "credit"})


class Layer:
    """One drawn sub-model: its label, render type (None: its model names
    none) and the model as a dict."""

    def __init__(self, label: str, render_type: str | None, model: dict):
        self.label, self.render_type, self.model = label, render_type, model


# -- Forge 1.12 multi-layer blockstates ---------------------------------------

def _variant(variants: dict, defaults: dict, key: str) -> tuple[dict | None, str]:
    """A Forge v1 variant composed with the defaults (Variant#sync: the
    variant's own keys win), or why it can't be read."""
    value = variants.get(key)
    if isinstance(value, list):
        if len(value) != 1:
            return None, f"variant {key!r} has {len(value)} weighted alternates"
        value = value[0]
    if not isinstance(value, dict):
        return None, f"variant {key!r} isn't a fully specified variant"
    out = dict(defaults)
    for k, v in value.items():
        if k in ("textures", "custom") and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out, ""


def is_forge_multilayer(blockstate: object) -> bool:
    """A Forge v1 blockstate whose ``normal`` variant is a multi-layer model."""
    if not isinstance(blockstate, dict) or blockstate.get("forge_marker") != 1:
        return False
    variants = blockstate.get("variants")
    defaults = blockstate.get("defaults") if isinstance(blockstate.get("defaults"), dict) else {}
    if not isinstance(variants, dict) or "normal" not in variants:
        return False
    entry, _ = _variant(variants, defaults, "normal")
    return entry is not None and entry.get("model") == MULTI_LAYER


def _location(mod: SourceMod, location: object, here: str) -> tuple[dict | None, str, str]:
    """A ``ModelResourceLocation`` (``ns:path#variant``; no ``#`` is the
    ``normal`` variant) as a composed model: the Forge v1 blockstate
    ``ns:path``'s variant, its model under ``block/`` (getBlockLocation,
    L446-450) retextured by the variant's textures. Returns (model, the
    blockstate name it came from, why)."""
    if not isinstance(location, str) or not location:
        return None, "", f"layer location {location!r} isn't a model location"
    where, _, variant = location.partition("#")
    ns, _, path = where.rpartition(":")
    ns = ns or "minecraft"
    if ns != mod.namespace:
        return None, "", f"layer location {location!r} is in another namespace"
    file = mod.assets / "blockstates" / f"{path}.json"
    if path == here:
        body = None
    elif not file.is_file():
        return None, "", f"layer location {location!r} names a blockstate that isn't in the mod"
    else:
        try:
            body = json.loads(file.read_text())
        except json.JSONDecodeError:
            return None, "", f"layer location {location!r} names an invalid blockstate"
    return {"_blockstate": body, "_path": path, "_variant": variant or "normal"}, path, ""


def _layer_model(mod: SourceMod, blockstate: dict, ref: dict) -> tuple[dict | None, str]:
    body = blockstate if ref["_blockstate"] is None else ref["_blockstate"]
    key = ref["_variant"]
    if not isinstance(body, dict) or body.get("forge_marker") != 1:
        return None, f"layer blockstate {ref['_path']!r} isn't a Forge blockstate (forge_marker 1)"
    variants = body.get("variants") if isinstance(body.get("variants"), dict) else {}
    defaults = body.get("defaults") if isinstance(body.get("defaults"), dict) else {}
    if key not in variants:
        return None, f"layer variant {ref['_path']}#{key} isn't in its blockstate"
    entry, why = _variant(variants, defaults, key)
    if entry is None:
        return None, f"layer {ref['_path']}#{key}: {why}"
    model = entry.get("model")
    if not isinstance(model, str) or model == MULTI_LAYER:
        return None, f"layer {ref['_path']}#{key} names no JSON model"
    transform = entry.get("transform")
    if transform is not None and transform not in _PERSPECTIVE_ONLY:
        return None, f"layer {ref['_path']}#{key} sets transform {transform!r}, which isn't read"
    # custom data is ignored by a JSON model (IModel#process returns the model
    # itself, IModel.java L89-91), so the inherited multi-layer keys are moot.
    extra = sorted(set(entry) - {"model", "textures", "custom", "transform"})
    if extra:
        return None, f"layer {ref['_path']}#{key} sets {', '.join(extra)}, which isn't read"
    textures = entry.get("textures") or {}
    if not isinstance(textures, dict) or not all(isinstance(v, str) and v for v in textures.values()):
        return None, f"layer {ref['_path']}#{key} removes or misnames a texture"
    ns, _, path = model.rpartition(":")
    composed = {"parent": f"{ns or 'minecraft'}:block/{path}"}
    if textures:
        composed["textures"] = dict(textures)
    return composed, ""


def forge_layers(mod: SourceMod, name: str, blockstate: dict) -> tuple[list[Layer] | None, dict | None, str]:
    """(every layer the multi-layer ``normal`` variant names, as
    :class:`Layer` with its 1.12 layer as ``label``; the ``base`` model; why
    not). Every other variant of the blockstate must be one a layer location
    names (a model holder), so ``normal`` is the only one a placed block
    shows."""
    variants = blockstate["variants"]
    defaults = blockstate.get("defaults") if isinstance(blockstate.get("defaults"), dict) else {}
    entry, why = _variant(variants, defaults, "normal")
    if entry is None:
        return None, None, why
    extra = sorted(set(entry) - {"model", "custom", "transform"})
    if extra:
        return None, None, f"its multi-layer variant sets {', '.join(extra)}, which isn't read"
    if entry.get("transform") is not None and entry["transform"] not in _PERSPECTIVE_ONLY:
        return None, None, f"its multi-layer variant sets transform {entry['transform']!r}, which isn't read"
    custom = entry.get("custom")
    if not isinstance(custom, dict) or not custom:
        return None, None, "its multi-layer variant names no layer models (custom)"
    layers: list[Layer] = []
    base = None
    named: set[str] = set()
    for key, location in custom.items():
        if key != "base" and key not in LAYER_NAMES_112:
            continue  # MultiLayerModel#process keeps base and layer names only
        ref, path, why = _location(mod, location, name)
        if ref is None:
            return None, None, why
        if path == name:
            named.add(ref["_variant"])
        model, why = _layer_model(mod, blockstate, ref)
        if model is None:
            return None, None, why
        if key == "base":
            base = model
        else:
            layer = LAYER_NAMES_112[key]
            layers.append(Layer(layer, RENDER_TYPE_112[layer], model))
    if not layers:
        return None, None, "its multi-layer variant names no render layer model"
    others = sorted(k for k in variants if k != "normal" and k not in named)
    if others:
        return None, None, (f"the blockstate also has variant(s) {', '.join(others[:3])} no layer names, "
                            "so the block may have states besides normal")
    order = list(LAYER_NAMES_112.values())
    layers.sort(key=lambda layer: order.index(layer.label))
    return layers, base, ""


# -- NeoForge/Forge composite models ------------------------------------------

def is_composite(model: object) -> bool:
    return isinstance(model, dict) and model.get("loader") in COMPOSITE_LOADERS


def composite(mod: SourceMod, model: dict) -> tuple[dict | None, list[Path], set, str]:
    """A composite model as one model with elements: (the merged model, the
    files read, the children's render types, why not)."""
    loader = model.get("loader")
    unread = sorted(set(model) - _COMPOSITE_KEYS)
    if unread:
        return None, [], set(), f"composite model ({loader}) sets {', '.join(unread)}, which isn't read"
    children = model.get("children")
    if not isinstance(children, dict) or not children:
        return None, [], set(), f"composite model ({loader}) has no children"
    visibility = model.get("visibility") or {}
    if not isinstance(visibility, dict):
        return None, [], set(), f"composite model ({loader}) has a visibility that isn't a map"
    layers = []
    for label, child in children.items():
        if visibility.get(label) is False:
            continue  # bake skips a hidden child (L77-80)
        if not isinstance(child, dict):
            return None, [], set(), f"composite child {label!r} isn't a model"
        layers.append(Layer(label, None, child))
    if not layers:
        return None, [], set(), f"composite model ({loader}) hides every child"
    merged, files, types, why = merge(mod, layers)
    if merged is None:
        return None, files, types, f"composite model ({loader}): {why}"
    if "ambientocclusion" in model:
        merged["ambientocclusion"] = model["ambientocclusion"]
    else:
        merged.pop("ambientocclusion", None)
    particle = (model.get("textures") or {}).get("particle") if isinstance(model.get("textures"), dict) else None
    if isinstance(particle, str) and not particle.startswith("#"):
        merged["textures"]["particle"] = particle
    return merged, files, types, ""


# -- merging ------------------------------------------------------------------

def merge(mod: SourceMod, layers: list[Layer]) -> tuple[dict | None, list[Path], set, str]:
    """The layers' elements as one flat model (textures renamed
    ``<layer>_<key>`` where two layers use one key for different textures),
    the files read, the render types, and why not. A layer whose
    ``render_type`` is None takes the one its own model names."""
    files: list[Path] = []
    textures: dict[str, str] = {}
    elements: list[dict] = []
    worn: dict[str, set] = {}
    sampled: dict[str, list] = {}  # render type -> (texture key, face uv or None)
    types: list[str | None] = []
    ao = None
    for index, layer in enumerate(layers):
        seen: set = set()
        token = models.RENDER_TYPES_SEEN.set(seen)
        try:
            flat, read, why = models.resolve(mod, layer.model)
        finally:
            models.RENDER_TYPES_SEEN.reset(token)
        files += [p for p in read if p not in files]
        if why:
            return None, files, set(), f"layer {layer.label!r}: {why}"
        if not flat.get("elements"):
            flat, why = models.expand_template(flat, mod.minecraft)
            if flat is None or not flat.get("elements"):
                return None, files, set(), f"layer {layer.label!r} has no elements: {why or 'none read'}"
        rtype = layer.render_type
        if rtype is None:
            named = {t for t in seen if t is not None}
            rtype = models.normalize(named.pop()) if len(named) == 1 else None
        types.append(rtype)
        if index == 0:
            ao = flat.get("ambientocclusion")
        own = flat.get("textures") or {}
        rename: dict[str, str] = {}
        for key, value in own.items():
            new = key
            if key in textures and textures[key] != value:
                new = f"{layer.label.lower().replace(' ', '_')}_{key}"
                if new in textures and textures[new] != value:
                    return None, files, set(), f"layer {layer.label!r} texture {key!r} can't be renamed apart"
            rename[key] = new
            textures[new] = value
        keys = worn.setdefault(rtype, set())
        for element in flat["elements"]:
            element = json.loads(json.dumps(element))
            for face in (element.get("faces") or {}).values():
                ref = face.get("texture") if isinstance(face, dict) else None
                if isinstance(ref, str) and ref.startswith("#"):
                    if ref[1:] not in rename:
                        # Java draws the missing texture there; merged, the
                        # face would wear another layer's texture of that name.
                        return None, files, set(), f"layer {layer.label!r} has a face naming {ref}, which it doesn't set"
                    face["texture"] = "#" + rename[ref[1:]]
                    keys.add(face["texture"][1:])
                    uv = face.get("uv")
                    sampled.setdefault(rtype, []).append((face["texture"][1:], uv if isinstance(uv, list) else None))
            elements.append(element)
    merged = {"textures": textures, "elements": elements}
    if ao is not None:
        merged["ambientocclusion"] = ao
    kinds = set(types)
    if len(kinds) > 1:
        if None in kinds:
            return None, files, kinds, ("one layer names its render type and another doesn't (the block's code "
                                        "decides that one), so the shared render method isn't read")
        if kinds == {_SOLID, _TRANSLUCENT}:
            # DEFAULT (pick 1a): drawn wholly blend (shared_type). Exact for
            # the solid layer only where each of its faces samples opaque
            # pixels (blend would show a transparent pixel Java's solid
            # layer draws opaque).
            for key, uv in sampled.get(_SOLID, ()):
                why = _opaque(mod, textures.get(key), uv)
                if why:
                    return None, files, kinds, (f"its layers draw in minecraft:solid and minecraft:translucent, and "
                                                f"its solid layer's texture {textures.get(key)!r} {why}, so blend "
                                                "(the one method its translucent layer needs) isn't shown to draw "
                                                "the solid layer the same")
            return merged, files, kinds, ""
        if kinds - _CUTOUT - {_SOLID}:
            # The blend DEFAULT (pick 1a) is for solid beside translucent
            # only: blend would draw a cutout layer's partly transparent
            # pixels see-through, which Java's cutout layer draws opaque.
            return None, files, kinds, (f"its layers draw in {', '.join(sorted(kinds))}; Bedrock gives a block one "
                                        "render method (#262), and no one method draws a translucent layer and "
                                        "another layer the same as Java (the blend DEFAULT covers a solid layer "
                                        "beside a translucent one only)")
        for key in sorted(worn.get(_SOLID, ())):
            why = _opaque(mod, textures.get(key))
            if why:
                return None, files, kinds, (f"its solid layer's texture {textures.get(key)!r} {why}, so alpha_test "
                                            "(the one method its cutout layer needs) isn't shown to draw it the same")
    return merged, files, kinds, ""


def _opaque(mod: SourceMod, reference: object, uv: list | None = None) -> str:
    """Why a texture isn't shown fully opaque, or "" when it is (the mod's
    own PNG with no transparent pixel). With a face ``uv`` (Java's 0-16
    texture units) only the pixels that face samples are checked; a face
    without one, or a texture that isn't one square frame, is checked whole."""
    if not isinstance(reference, str) or reference.startswith("#"):
        return "isn't set"
    ns, _, path = reference.rpartition(":")
    if (ns or "minecraft") != mod.namespace:
        return "is another namespace's, whose pixels aren't read"
    file = mod.assets / "textures" / f"{path}.png"
    if not file.is_file():
        return "isn't in the mod"
    data = file.read_bytes()
    if uv is not None and len(uv) == 4 and all(isinstance(v, (int, float)) for v in uv):
        decoded = png_reader.decode_rgba(data)
        if decoded is None:
            return "can't be read"
        width, height, rgba = decoded
        if width == height:
            x0, x1 = sorted((uv[0], uv[2]))
            y0, y1 = sorted((uv[1], uv[3]))
            scale = width / 16
            # A zero-width uv still samples the pixel it sits on.
            cols = range(max(0, int(x0 * scale)), min(width, max(int(x0 * scale) + 1, math.ceil(x1 * scale))))
            rows = range(max(0, int(y0 * scale)), min(height, max(int(y0 * scale) + 1, math.ceil(y1 * scale))))
            if any(rgba[(y * width + x) * 4 + 3] < 255 for y in rows for x in cols):
                return "has transparent pixels where a face samples it"
            return ""
    clear = png_reader.has_transparency(data)
    if clear is None:
        return "can't be read"
    return "has transparent pixels" if clear else ""


def shared_type(types: set) -> tuple[str | None, str]:
    """The one render type the merged block draws in, and why: one type as
    it is; solid beside cutout as the cutout type (merge checked the solid
    textures are opaque, so alpha_test draws them the same)."""
    names = {t for t in types if t is not None}
    if len(names) == 1:
        return next(iter(names)), ""
    if names == {_SOLID, _TRANSLUCENT}:
        return BLEND_DEFAULT, BLEND_DEFAULT_WHY  # merge checked the solid faces sample opaque pixels
    cut = names & _CUTOUT
    if cut and names <= cut | {_SOLID}:
        if _SOLID not in names:
            return min(cut), ""  # every cutout type draws alpha_test
        return (min(cut), "its solid layer's textures have no transparent pixel, so they draw the same as "
                          "alpha_test, the method its cutout layer needs")
    return None, ""
