"""Pre-baked icons for Tinkers' Construct tools (#122).

Tinkers ships one pre-rendered sprite per tool part and material
(``tool/pickaxe/head_tconstruct_iron.png``), about 11.7k of them, and composes a
tool's look at runtime: its item model (``"loader": "tconstruct:tool"``) names a
texture per part, and Java code picks each part's material sprite from the
stack's NBT. Bedrock has no per-stack icon, so none of those sprites is ever
shown by a converted item.

What *is* in data is which tools Tinkers itself puts in its creative tab.
``ToolBuildHandler.addVariants`` (Java, 1.20.1) adds, per tool, one stack per
visible material: every part that can use that material gets it, every other
part gets the first visible material with its stat type, and a material that no
part can use adds nothing. Visible means not ``hidden``; order is tier, then
``sortOrder`` (100 when absent), then id (``IMaterial.compareTo``). All of that
is JSON in the jar:

- ``data/<ns>/tinkering/materials/definition/*.json``: hidden, tier, sortOrder,
  and a forge ``condition``/``redirect`` (we skip those: whether they load
  depends on other mods and config, which we can't see).
- ``data/<ns>/tinkering/materials/stats/*.json``: the stat types a material has.
- ``data/<ns>/tinkering/tool_definitions/*.json``: the stat type of each
  material slot, directly (``material_stats``) or through a part item
  (``part_stats``), whose model texture ``generator_part_textures.json`` maps
  to a stat type.
- ``assets/<ns>/tinkering/materials/**.json``: render info, i.e. the sprite
  suffix, fallbacks and tint, resolved the way ``MaterialRenderInfo.getSprite``
  does: the material's own sprite untinted, else a fallback sprite tinted by
  ``color``, else the part's base sprite tinted.

So the creative-tab tools are pre-baked here: each one's part sprites,
alpha-composited in the model's ``parts`` order, become one item icon (the
sprites' size, 16x16 in Tinkers) under
``textures/items/tinkers_presets/<tool>/<material>.png`` with an
``item_texture.json`` key ``<ns>:tinkers_<tool>_<material>``. It is a pure
function of the jar: same jar, same bytes.

What this does not do, on purpose:

- No Bedrock *items*. A tool's stats, traits, modifiers, tool station and part
  builder are Java code. ``items.convert`` already refuses tool models for that
  reason (an item that looks like a pickaxe and mines like a fist), and so the
  icons ship as textures a later step can bind to an item once someone decides
  what that item may honestly claim. No stats or recipes are invented here.
- Modifier overlays are not drawn: creative-tab stacks carry none.
- An animated sprite (``.mcmeta``) contributes its first frame, and an emissive
  material (``luminosity``) is drawn unlit; both are reported as notes.

A tool this can't resolve (an unknown stat type for a slot, a missing sprite, a
size mismatch) bakes nothing, and says why in the residue.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import png
from ..model import ConversionResult, SourceMod, Unhandled

_TOOL_LOADER = "tconstruct:tool"
_PRESET_DIR = "textures/items/tinkers_presets"
_INDEX = "textures/item_texture.json"
_DEFAULT_SORT = 100  # MaterialManager.loadMaterial: sortOrder defaults to 100


@dataclass(frozen=True)
class Material:
    name: str  # path part of the id, e.g. "iron"
    tier: int
    sort: int
    stats: frozenset[str]

    def key(self):
        # IMaterial.compareTo: tier, sort order, then ResourceLocation (path
        # first; one namespace here, so the path decides).
        return (self.tier, self.sort, self.name)


@dataclass
class Bake:
    """What one run produced, kept for the report and the tests."""

    presets: dict[str, list[str]] = field(default_factory=dict)  # tool -> materials
    sprites_used: set[str] = field(default_factory=set)  # mod-relative sprite paths
    animated: set[str] = field(default_factory=set)
    emissive: set[str] = field(default_factory=set)
    skipped_conditional: list[str] = field(default_factory=list)
    render_files: set[Path] = field(default_factory=set)  # render info actually read


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _local(ref: str, namespace: str) -> str | None:
    """``ns:path`` -> ``path`` when it is this mod's namespace, else None."""
    ns, _, rest = ref.rpartition(":")
    if ns and ns != namespace:
        return None
    return rest


def _stat_id(entry) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("stat"), str):
        return entry["stat"]
    return None


def _materials(mod: SourceMod, bake: Bake) -> list[Material]:
    root = mod.data / "tinkering" / "materials"
    out = []
    for path in sorted((root / "definition").glob("*.json")):
        body = _read_json(path)
        if not isinstance(body, dict) or not body:
            continue
        if "condition" in body or "redirect" in body:
            # Loaded or redirected depending on other mods and config: not
            # something the jar alone decides.
            bake.skipped_conditional.append(path.stem)
            continue
        if body.get("hidden") is True:
            continue
        stats = _read_json(root / "stats" / path.name)
        stat_types = frozenset((stats or {}).get("stats") or {}) if isinstance(stats, dict) else frozenset()
        tier = body.get("tier", 0)
        sort = body.get("sortOrder", _DEFAULT_SORT)
        if not isinstance(tier, int) or not isinstance(sort, int):
            continue
        out.append(Material(path.stem, tier, sort, stat_types))
    return sorted(out, key=Material.key)


@dataclass(frozen=True)
class RenderInfo:
    texture: str | None  # sprite suffix, or None for "always tint the base"
    fallbacks: tuple[str, ...]
    color: tuple[int, int, int, int]  # RGBA multipliers, 0-255
    luminosity: int


# A layer with no material: the base sprite itself, untinted.
_PLAIN = RenderInfo(None, (), (255, 255, 255, 255), 0)


def _color(value) -> tuple[int, int, int, int]:
    """Mantle ColorLoadable.ALPHA: AARRGGBB, or RRGGBB meaning opaque."""
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        try:
            n = int(text, 16)
        except ValueError:
            return (255, 255, 255, 255)
        if len(text) <= 6:
            n |= 0xFF000000
        return ((n >> 16) & 255, (n >> 8) & 255, n & 255, (n >> 24) & 255)
    if isinstance(value, int):
        return ((value >> 16) & 255, (value >> 8) & 255, value & 255, (value >> 24) & 255)
    return (255, 255, 255, 255)


def _render_json(root: Path, rel: str, read: set[Path], seen: tuple = ()) -> dict | None:
    path = root / f"{rel}.json"
    body = _read_json(path)
    if not isinstance(body, dict):
        return None
    read.add(path)
    parent = body.get("parent")
    if isinstance(parent, str) and parent not in seen:
        _, _, prel = parent.rpartition(":")
        base = _render_json(root, prel, read, (*seen, rel)) or {}
        merged = dict(base)
        merged.update({k: v for k, v in body.items() if k != "parent"})
        return merged
    return body


def _render_info(mod: SourceMod, material: str, read: set[Path] | None = None) -> RenderInfo:
    root = mod.assets / "tinkering" / "materials"
    body = _render_json(root, material, read if read is not None else set()) or {}
    if "texture" in body:
        tex = body["texture"]
        if tex is None:
            suffix = None
        else:
            ns, _, path = str(tex).rpartition(":")
            # MaterialRenderInfo.getSuffix: minecraft namespace means a bare name.
            suffix = path if ns == "minecraft" else f"{ns or mod.namespace}_{path}"
    elif body.get("skipUniqueTexture") is True:
        suffix = None
    else:
        suffix = f"{mod.namespace}_{material}"
    fallbacks = tuple(f for f in body.get("fallbacks") or () if isinstance(f, str))
    lum = body.get("luminosity", 0)
    return RenderInfo(suffix, fallbacks, _color(body.get("color", "FFFFFFFF")), lum if isinstance(lum, int) else 0)


def _texture_stat_types(mod: SourceMod) -> dict[str, str]:
    """Texture path (no namespace) -> stat type, from generator_part_textures.json."""
    body = _read_json(mod.assets / "tinkering" / "generator_part_textures.json")
    parts = body.get("parts") if isinstance(body, dict) else None
    out = {}
    for part in parts if isinstance(parts, list) else ():
        if isinstance(part, dict) and isinstance(part.get("path"), str) and isinstance(part.get("stat_type"), str):
            local = _local(part["path"], mod.namespace)
            if local is not None:
                out[local] = part["stat_type"]
    return out


def _part_stat_type(mod: SourceMod, part_item: str, by_texture: dict[str, str]) -> str | None:
    """A part item's stat type: its item model names a texture the generator maps."""
    name = _local(part_item, mod.namespace)
    if name is None:
        return None
    model = _read_json(mod.assets / "models" / "item" / f"{name}.json")
    if not isinstance(model, dict):
        return None
    for ref in (model.get("textures") or {}).values():
        if isinstance(ref, str):
            local = _local(ref, mod.namespace)
            if local in by_texture:
                return by_texture[local]
    return None


def _slot_stat_types(mod: SourceMod, tool: str, by_texture: dict[str, str]) -> tuple[list[str] | None, str]:
    """Stat type per material slot of a tool definition, or (None, why)."""
    body = _read_json(mod.data / "tinkering" / "tool_definitions" / f"{tool}.json")
    if not isinstance(body, dict):
        return None, "no tool definition"
    for module in body.get("modules") or ():
        if not isinstance(module, dict):
            continue
        kind = module.get("type")
        if kind == "tconstruct:material_stats":
            slots = [_stat_id(s) for s in module.get("stat_types") or ()]
            if None in slots:
                return None, "a material_stats entry names no stat type"
            return slots, ""
        if kind == "tconstruct:part_stats":
            slots = []
            for part in module.get("parts") or ():
                item = part if isinstance(part, str) else (part.get("item") if isinstance(part, dict) else None)
                stat = _part_stat_type(mod, item, by_texture) if isinstance(item, str) else None
                if stat is None:
                    return None, f"cannot tell the stat type of part {item!r}"
                slots.append(stat)
            return slots, ""
    return [], ""  # no materials: a fixed-texture tool


def _sprite(mod: SourceMod, rel: str) -> tuple[int, int, bytes, bool] | None:
    """Decoded sprite at textures/<rel>.png: (w, h, rgba, animated)."""
    path = mod.assets / "textures" / f"{rel}.png"
    if not path.is_file():
        return None
    decoded = png.decode_rgba(path.read_bytes())
    if decoded is None:
        return None
    w, h, rgba = decoded
    animated = path.with_name(path.name + ".mcmeta").is_file()
    if animated and h > w and h % w == 0:
        rgba = rgba[: w * w * 4]  # first frame of a vertical strip
        h = w
    return w, h, rgba, animated


def _tint(rgba: bytes, color: tuple[int, int, int, int]) -> bytes:
    if color == (255, 255, 255, 255):
        return rgba
    r, g, b, a = color
    out = bytearray(rgba)
    for i in range(0, len(out), 4):
        out[i] = out[i] * r // 255
        out[i + 1] = out[i + 1] * g // 255
        out[i + 2] = out[i + 2] * b // 255
        out[i + 3] = out[i + 3] * a // 255
    return bytes(out)


def _over(dst: bytearray, src: bytes) -> None:
    """Source-over alpha compositing, integer math so the bytes are stable."""
    for i in range(0, len(src), 4):
        sa = src[i + 3]
        if sa == 0:
            continue
        if sa == 255:
            dst[i : i + 4] = src[i : i + 4]
            continue
        da = dst[i + 3]
        out_a = sa + da * (255 - sa) // 255
        if out_a == 0:
            continue
        for c in range(3):
            num = src[i + c] * sa * 255 + dst[i + c] * da * (255 - sa)
            dst[i + c] = num // (out_a * 255)
        dst[i + 3] = out_a


def _layer(mod: SourceMod, base: str, info: RenderInfo, bake: Bake):
    """The sprite for one part in one material, as MaterialRenderInfo.getSprite."""
    candidates = []
    if info.texture is not None:
        candidates.append((f"{base}_{info.texture}", False))
    candidates += [(f"{base}_{fb}", True) for fb in info.fallbacks]
    candidates.append((base, True))
    for rel, tinted in candidates:
        found = _sprite(mod, rel)
        if found is None:
            continue
        w, h, rgba, animated = found
        if animated:
            bake.animated.add(rel)
        bake.sprites_used.add(f"assets/{mod.namespace}/textures/{rel}.png")
        return w, h, _tint(rgba, info.color) if tinted else rgba
    return None


def _tool_models(mod: SourceMod) -> dict[str, dict]:
    src = mod.assets / "models" / "item"
    out = {}
    for path in sorted(src.glob("*.json")) if src.is_dir() else ():
        body = _read_json(path)
        if isinstance(body, dict) and body.get("loader") == _TOOL_LOADER:
            out[path.stem] = body
    return out


def applies(mod: SourceMod) -> bool:
    return (mod.assets / "tinkering" / "generator_part_textures.json").is_file() and bool(
        _tool_models(mod)
    )


def bake(mod: SourceMod) -> tuple[ConversionResult, Bake]:
    result = ConversionResult()
    info = Bake()
    if not applies(mod):
        return result, info

    by_texture = _texture_stat_types(mod)
    materials = _materials(mod, info)
    first_with: dict[str, Material | None] = {}

    def first(stat: str) -> Material | None:
        if stat not in first_with:
            first_with[stat] = next((m for m in materials if stat in m.stats), None)
        return first_with[stat]

    renders: dict[str, RenderInfo] = {}
    index: dict[str, dict] = {}
    for tool, model in _tool_models(mod).items():
        source = f"assets/{mod.namespace}/models/item/{tool}.json"
        textures = model.get("textures") or {}
        parts = model.get("parts")
        slots, why = _slot_stat_types(mod, tool, by_texture)
        if slots is None:
            result.unhandled.append(Unhandled(source, "tinkers_preset", f"no preset icons: {why}"))
            continue
        if not slots or not parts:
            # A fixed-texture tool (staffs, flint and brick) already has its one
            # icon among the converted textures; nothing to compose.
            continue

        layers = []
        bad = None
        for part in parts:
            name, slot = (part.get("name"), part.get("index")) if isinstance(part, dict) else (None, None)
            ref = textures.get(name) if isinstance(name, str) else None
            base = _local(ref, mod.namespace) if isinstance(ref, str) else None
            if base is None:
                bad = f"part {part!r} names no texture of this mod"
                break
            if slot is None:
                layers.append((base, None))  # a fixed layer, drawn as shipped
                continue
            if not isinstance(slot, int) or not 0 <= slot < len(slots):
                bad = f"part {part!r} points at no material slot of the tool definition"
                break
            layers.append((base, slot))
        if bad:
            result.unhandled.append(Unhandled(source, "tinkers_preset", f"no preset icons: {bad}"))
            continue

        baked = []
        for material in materials:
            picks = []
            used = False
            for stat in slots:
                if stat in material.stats:
                    picks.append(material)
                    used = True
                else:
                    picks.append(first(stat))
            if not used or None in picks:
                continue
            canvas = None
            size = None
            for base, slot in layers:
                if slot is None:
                    drawn = _layer(mod, base, _PLAIN, info)
                else:
                    pick = picks[slot]
                    if pick.name not in renders:
                        renders[pick.name] = _render_info(mod, pick.name, info.render_files)
                    render = renders[pick.name]
                    if render.luminosity:
                        info.emissive.add(pick.name)
                    drawn = _layer(mod, base, render, info)
                if drawn is None:
                    bad = f"no sprite for {base} in {pick.name}"
                    break
                w, h, rgba = drawn
                if canvas is None:
                    canvas, size = bytearray(w * h * 4), (w, h)
                elif (w, h) != size:
                    bad = f"{base} is {w}x{h}, other layers are {size[0]}x{size[1]}"
                    break
                _over(canvas, rgba)
            if bad:
                break
            key = f"tinkers_{tool}_{material.name}"
            if any((mod.assets / "textures" / d / f"{key}.png").is_file() for d in ("item", "items")):
                # The textures converter owns that index key already.
                bad = f"index key {mod.namespace}:{key} is taken by a texture of the mod"
                break
            path = f"{_PRESET_DIR}/{tool}/{material.name}"
            result.files[f"{path}.png"] = png.encode_png(size[0], size[1], bytes(canvas))
            index[f"{mod.namespace}:{key}"] = {"textures": path}
            baked.append(material.name)
        if bad:
            for material_name in baked:
                result.files.pop(f"{_PRESET_DIR}/{tool}/{material_name}.png", None)
                index.pop(f"{mod.namespace}:tinkers_{tool}_{material_name}", None)
            result.unhandled.append(Unhandled(source, "tinkers_preset", f"no preset icons: {bad}"))
            continue
        if baked:
            info.presets[tool] = baked

    if index:
        result.files[_INDEX] = {
            "resource_pack_name": mod.namespace,
            "texture_name": "atlas.items",
            "texture_data": index,
        }
        # The render info the icons were drawn from converted into them. Only
        # what was read: a variant's render info (wood/crimson) drew nothing.
        for path in sorted(info.render_files):
            result.claim(mod, path)
        result.claim(mod, mod.assets / "tinkering" / "generator_part_textures.json")
        total = sum(len(v) for v in info.presets.values())
        result.notes.append(
            f"tinkers: pre-baked {total} creative-tab tool icons for {len(info.presets)} tools "
            f"from {len(info.sprites_used)} part sprites; they ship as textures only, since "
            "tool stats, traits and modifiers are Java code"
        )
        if info.animated:
            result.notes.append(
                f"tinkers: {len(info.animated)} animated part sprite(s) drawn as their first frame "
                "in the pre-baked icons"
            )
        if info.emissive:
            result.notes.append(
                f"tinkers: glowing materials drawn unlit in the pre-baked icons: {', '.join(sorted(info.emissive))}"
            )
        if info.skipped_conditional:
            result.notes.append(
                "tinkers: materials that load only with other mods or config got no preset icons: "
                + ", ".join(info.skipped_conditional)
            )
    return result, info


def convert(mod: SourceMod) -> ConversionResult:
    return bake(mod)[0]
