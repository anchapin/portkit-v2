"""Pre-baked icons and display-only items for Tinkers' Construct tools (#122, #128).

Moved from ``converters/tinkers.py`` into the Tinkers' Construct adapter
(#245): the core reaches it only through the adapter's ``convert`` hook (run
by :func:`portkit.converters.adapter_data`) and its ``item_models`` hook (asked
by :func:`portkit.converters.items.convert`, which leaves these models alone).

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

Each baked preset also becomes a **display-only** Bedrock item
(``<ns>:tinkers_<tool>_<material>``): the icon, a display name and
``max_stack_size`` 1, and nothing else (#128, decided 2026-10-11). A tool's
mining speed, damage, durability, traits and modifiers come from Java code, so
the item carries none of them, and the report says so. This is the one place
portkit ships an item it knows is behaviorally empty; see the decision log.

Tool *parts* (``pick_head``, ``tool_binding``, …) become plain items too,
inert like an ingot: one per part and visible material, when the material has
the part's stat type (``ToolPartItem.canUseMaterial``) and the jar ships that
material's own sprite for the part. The icon is that sprite, already converted
by the textures converter, so nothing is composited. A repair kit takes any
repairable material in Java, which is decided in code, so repair kits are
made only for materials whose stats name the repair-kit stat type.

Names come from the mod's own lang files, composed the way Tinkers composes
them: ``MaterialItem.getName`` for parts, and the tool definition's
``fixed_material_name`` / ``material_name`` (filter ``all``) modules for
tools. A tool whose name rule is decided in Java (no name module, so
``canRepair``; ``unique_material_name``; ``custom_material_name``) keeps the
tool's own name ("Pickaxe"). A locale missing a key falls back to ``en_us``,
as Java does. The lines join the lang converter's ``texts/<Locale>.lang``.

What this does not do, on purpose:

- No stats, recipes or behavior. A tool's stats, traits, modifiers, tool
  station and part builder are Java code; ``items.convert`` refuses tool
  models for that reason (an item that looks like a pickaxe and mines like a
  fist), and the items here say they're display-only instead of pretending.
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

from ... import png
from ...converters import models
from ...converters.lang import _LOCALES, _one_line
from ...model import ConversionResult, SourceMod, Unhandled

_TOOL_LOADER = "tconstruct:tool"
_PART_LOADER = "tconstruct:material"
_ITEM_FORMAT = "1.20.10"  # the items converter's format_version
_MENU_CATEGORY = "items"
_TOOL_STACK = 1  # a Tinkers tool never stacks
_PART_STACK = 64  # a part item is a plain Java item: default stack size
_REPAIR_KIT_STAT = "tconstruct:repair_kit"
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
    parts: dict[str, list[str]] = field(default_factory=dict)  # part item -> materials
    named_by_base: list[str] = field(default_factory=list)  # tools named without material
    unnamed: list[str] = field(default_factory=list)  # item ids with no lang name at all
    repair_kit: bool = False  # a part whose materials Java picks in code


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


class _Lang:
    """The mod's lang files, looked up the way Java does: the locale, then en_us."""

    _PRIMARY = "en_us"

    def __init__(self, mod: SourceMod):
        self.tables: dict[str, dict[str, str]] = {}
        src = mod.assets / "lang"
        for path in sorted(src.glob("*.json")) if src.is_dir() else ():
            locale = path.stem.lower()
            body = _read_json(path)
            if locale in _LOCALES and isinstance(body, dict):
                self.tables[locale] = {k: v for k, v in body.items() if isinstance(v, str)}
        self.primary = self.tables.get(self._PRIMARY, {})

    def get(self, locale: str, key: str) -> str | None:
        value = self.tables[locale].get(key)
        return value if value is not None else self.primary.get(key)


def _format(pattern: str, *args: str) -> str:
    """Java String.format for the %s / %n$s / %% a lang format uses."""
    out, i, auto = [], 0, 0
    while i < len(pattern):
        ch = pattern[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        j = i + 1
        digits = ""
        while j < len(pattern) and pattern[j].isdigit():
            digits += pattern[j]
            j += 1
        if digits and pattern[j : j + 2] == "$s":
            n = int(digits) - 1
            out.append(args[n] if 0 <= n < len(args) else "")
            i = j + 2
        elif pattern[i + 1 : i + 2] == "s":
            out.append(args[auto] if auto < len(args) else "")
            auto += 1
            i += 2
        elif pattern[i + 1 : i + 2] == "%":
            out.append("%")
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _material_name(lang: _Lang, locale: str, ns: str, material: str, item_name: str) -> str | None:
    """MaterialToolName.nameForMaterial: the material's own format, else "<material> <item>"."""
    key = f"material.{ns}.{material}"
    own = lang.get(locale, f"{key}.format")
    if own is not None:
        return _format(own, item_name)
    shown, pattern = lang.get(locale, key), lang.get(locale, f"item.{ns}.tool.format")
    if shown is None or pattern is None:
        return None
    return _format(pattern, shown, item_name)


def _name_rule(mod: SourceMod, tool: str):
    """The tool definition's display-name modules, when the name is decided by data.

    Returns ("fixed", index), ("all", None), or None when Java code decides it:
    no module (the default filters on ``canRepair``), or one we don't model.
    """
    body = _read_json(mod.data / "tinkering" / "tool_definitions" / f"{tool}.json")
    modules = body.get("modules") if isinstance(body, dict) else None
    named = [
        m for m in modules or ()
        if isinstance(m, dict) and isinstance(m.get("type"), str) and m["type"].endswith("_name")
    ]
    if len(named) != 1:
        return None
    kind = named[0]["type"]
    if kind == "tconstruct:fixed_material_name" and isinstance(named[0].get("index"), int):
        return ("fixed", named[0]["index"])
    if kind == "tconstruct:material_name" and named[0].get("filter") == "all":
        return ("all", None)
    return None


def _tool_names(mod, lang, tool, rule, picks) -> dict[str, str]:
    """Bedrock locale -> display name for one preset."""
    ns = mod.namespace
    out = {}
    for locale in sorted(lang.tables):
        item_name = lang.get(locale, f"item.{ns}.{tool}")
        if item_name is None:
            continue
        name = None
        if rule is not None and rule[0] == "fixed" and 0 <= rule[1] < len(picks):
            name = _material_name(lang, locale, ns, picks[rule[1]].name, item_name)
        elif rule is not None and rule[0] == "all":
            shown = list(dict.fromkeys(m.name for m in picks))
            if len(shown) == 1:
                name = _material_name(lang, locale, ns, shown[0], item_name)
            else:
                labels = [lang.get(locale, f"material.{ns}.{m}") for m in shown]
                sep = lang.get(locale, f"item.{ns}.tool.material_separator")
                pattern = lang.get(locale, f"item.{ns}.tool.format")
                if None not in labels and sep is not None and pattern is not None:
                    name = _format(pattern, sep.join(labels), item_name)
        out[_LOCALES[locale]] = name if name is not None else item_name
    return out


def _part_names(mod, lang, part, material) -> dict[str, str]:
    """Bedrock locale -> display name for one part item, as MaterialItem.getName."""
    ns = mod.namespace
    key = f"item.{ns}.{part}"
    mkey = f"material.{ns}.{material}"
    out = {}
    for locale in sorted(lang.tables):
        full = lang.get(locale, f"{key}.{ns}.{material}")
        base = lang.get(locale, key)
        own = lang.get(locale, f"{mkey}.format")
        shown, pattern = lang.get(locale, mkey), lang.get(locale, f"item.{ns}.tool.format")
        if full is not None:
            name = full
        elif base is None:
            continue
        elif own is not None:
            name = _format(own, base)
        elif shown is not None and pattern is not None:
            name = _format(pattern, shown, base)
        else:
            name = base
        out[_LOCALES[locale]] = name
    return out


def _item(identifier: str, icon: str, stack: int) -> dict:
    return {
        "format_version": _ITEM_FORMAT,
        "minecraft:item": {
            "description": {
                "identifier": identifier,
                "menu_category": {"category": _MENU_CATEGORY},
            },
            "components": {
                "minecraft:icon": icon,
                "minecraft:max_stack_size": stack,
            },
        },
    }


def _taken_names(mod: SourceMod) -> set[str]:
    """Item and block names the mod itself defines, which our ids must not reuse."""
    out = set()
    for sub in ("models/item", "blockstates"):
        d = mod.assets / sub
        if d.is_dir():
            out |= {p.stem for p in d.glob("*.json")}
    return out


def owns_model(model: dict) -> bool:
    """Whether this converter answers for an item model, in a mod it ``applies`` to.

    Tinkers tool and part models are drawn from NBT at runtime; the pre-bake
    turns them into items or reports why not, so ``items.convert``'s generic
    "not a flat icon" residue would be wrong for them.
    """
    return model.get("loader") in (_TOOL_LOADER, _PART_LOADER)


def _part_models(mod: SourceMod) -> dict[str, dict]:
    src = mod.assets / "models" / "item"
    out = {}
    for path in sorted(src.glob("*.json")) if src.is_dir() else ():
        body = _read_json(path)
        if isinstance(body, dict) and body.get("loader") == _PART_LOADER:
            out[path.stem] = body
    return out


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


def item_models(mod: SourceMod):
    """The adapter's ``item_models`` hook: :func:`owns_model` in a mod this
    pre-bake ``applies`` to, else None (``items.convert`` handles every model)."""
    return owns_model if applies(mod) else None


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
    lang = _Lang(mod)
    taken = _taken_names(mod)
    items: dict[str, dict] = {}  # output path -> item json
    names: dict[str, dict[str, str]] = {}  # bedrock locale -> lang key -> value
    item_models: set[str] = set()  # models that became at least one item

    def add_names(identifier: str, by_locale: dict[str, str]) -> None:
        if not by_locale:
            info.unnamed.append(identifier)
        for locale, value in by_locale.items():
            names.setdefault(locale, {})[f"item.{identifier}.name"] = _one_line(value)

    for tool, model in _tool_models(mod).items():
        source = f"assets/{mod.namespace}/models/item/{tool}.json"
        textures = model.get("textures") or {}
        parts = model.get("parts")
        slots, why = _slot_stat_types(mod, tool, by_texture)
        if slots is None:
            result.unhandled.append(Unhandled(source, "tinkers_preset", f"no preset icons: {why}"))
            continue
        if not slots or not parts:
            # A fixed-texture tool (staffs, flint and brick): its one texture
            # already ships with the converted textures, and there's no preset
            # to bake. It has no material to show, only Java behavior.
            result.unhandled.append(Unhandled(
                source, "tinkers_preset",
                "a fixed-texture Tinkers tool: no material presets to bake, and its "
                "behavior is Java code",
            ))
            continue
        rule = _name_rule(mod, tool)

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
        pending: list[tuple[str, dict, dict[str, str]]] = []  # item path, json, names
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
            if key in taken:
                bad = f"item name {mod.namespace}:{key} is taken by an item or block of the mod"
                break
            path = f"{_PRESET_DIR}/{tool}/{material.name}"
            result.files[f"{path}.png"] = png.encode_png(size[0], size[1], bytes(canvas))
            index[f"{mod.namespace}:{key}"] = {"textures": path}
            identifier = f"{mod.namespace}:{key}"
            pending.append((
                f"items/{key}.json",
                _item(identifier, identifier, _TOOL_STACK),
                _tool_names(mod, lang, tool, rule, picks),
            ))
            baked.append(material.name)
        if bad:
            for material_name in baked:
                result.files.pop(f"{_PRESET_DIR}/{tool}/{material_name}.png", None)
                index.pop(f"{mod.namespace}:tinkers_{tool}_{material_name}", None)
            result.unhandled.append(Unhandled(source, "tinkers_preset", f"no preset icons: {bad}"))
            continue
        if not baked:
            result.unhandled.append(Unhandled(
                source, "tinkers_preset", "no visible material fits this tool, so no preset to bake"
            ))
            continue
        info.presets[tool] = baked
        if rule is None:
            info.named_by_base.append(tool)
        for path, body, by_locale in pending:
            items[path] = body
            add_names(body["minecraft:item"]["description"]["identifier"], by_locale)
        item_models.add(source)

    # Part items: inert, one per part and visible material with its own sprite.
    for part, model in _part_models(mod).items():
        source = f"assets/{mod.namespace}/models/item/{part}.json"
        refs = [r for r in (model.get("textures") or {}).values() if isinstance(r, str)]
        base = _local(refs[0], mod.namespace) if len(refs) == 1 else None
        stat = _part_stat_type(mod, f"{mod.namespace}:{part}", by_texture)
        if base is None or stat is None:
            result.unhandled.append(Unhandled(
                source, "tinkers_part",
                "a Tinkers part model whose texture or stat type can't be read from data",
            ))
            continue
        if stat == _REPAIR_KIT_STAT:
            info.repair_kit = True
        made = []
        for material in materials:
            if stat not in material.stats:
                continue
            if material.name not in renders:
                renders[material.name] = _render_info(mod, material.name, info.render_files)
            suffix = renders[material.name].texture
            sprite_rel = f"{base}_{suffix}" if suffix is not None else None
            if sprite_rel is None or not (mod.assets / "textures" / f"{sprite_rel}.png").is_file():
                continue  # only a tinted fallback would show it: not a shipped sprite
            key = f"tinkers_{part}_{material.name}"
            identifier = f"{mod.namespace}:{key}"
            if key in taken or f"items/{key}.json" in items:
                result.unhandled.append(Unhandled(
                    source, "tinkers_part", f"item name {identifier} is already taken"
                ))
                continue
            icon, _ = models.texture_shortname(f"{mod.namespace}:{sprite_rel}", mod.namespace)
            items[f"items/{key}.json"] = _item(identifier, icon, _PART_STACK)
            add_names(identifier, _part_names(mod, lang, part, material.name))
            made.append(material.name)
        if made:
            info.parts[part] = made
            item_models.add(source)
        else:
            result.unhandled.append(Unhandled(
                source, "tinkers_part",
                "no visible material has this part's stat type and its own sprite",
            ))

    result.files.update(items)
    for locale, lines in names.items():
        result.files[f"texts/{locale}.lang"] = "".join(
            f"{line}\n" for line in sorted(f"{key}={value}" for key, value in lines.items())
        )
    if names:
        rest = sorted(k for k in names if k != "en_US")
        result.files["texts/languages.json"] = (["en_US"] if "en_US" in names else []) + rest
    for source in sorted(item_models):
        result.claim(mod, mod.root / source)
    if index or items:
        # The render info the icons and items were drawn from converted into
        # them. Only what was read: a variant's render info (wood/crimson) drew
        # nothing.
        for path in sorted(info.render_files):
            result.claim(mod, path)
        result.claim(mod, mod.assets / "tinkering" / "generator_part_textures.json")

    if index:
        result.files[_INDEX] = {
            "resource_pack_name": mod.namespace,
            "texture_name": "atlas.items",
            "texture_data": index,
        }
        total = sum(len(v) for v in info.presets.values())
        result.notes.append(
            f"tinkers: pre-baked {total} creative-tab tool icons for {len(info.presets)} tools "
            f"from {len(info.sprites_used)} part sprites"
        )
        result.notes.append(
            f"tinkers: the {total} preset tools ship as display-only items (icon, name, "
            "max_stack_size 1): mining speed, damage, durability, enchantability, traits and "
            "modifiers are Tinkers' Java code and are not converted, so in Bedrock they do "
            "nothing a tool does"
        )
        if info.named_by_base:
            result.notes.append(
                "tinkers: these tools name their material in Java code, so their display-only "
                "items carry the tool's own name: " + ", ".join(sorted(info.named_by_base))
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
                "tinkers: materials that load only with other mods or config got no preset icons "
                "or part items: " + ", ".join(info.skipped_conditional)
            )
    if info.unnamed:
        result.notes.append(
            f"tinkers: {len(info.unnamed)} item(s) have no name in the mod's lang files "
            "and show their identifier"
        )
    if info.parts:
        total_parts = sum(len(v) for v in info.parts.values())
        result.notes.append(
            f"tinkers: {total_parts} tool-part items ({len(info.parts)} parts × material) ship "
            "as plain items with the part's own sprite; their use in the tool station and "
            "part builder is Java code"
        )
        if info.repair_kit:
            result.notes.append(
                "tinkers: repair kits are made only for materials whose stats name the "
                "repair-kit stat type; Java also accepts any repairable material, which "
                "it decides in code"
            )
    return result, info


def convert(mod: SourceMod) -> ConversionResult:
    return bake(mod)[0]
