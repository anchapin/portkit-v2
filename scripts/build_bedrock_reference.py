#!/usr/bin/env python3
"""Regenerate src/portkit/agent/reference/bedrock_reference.json (#114).

The residue agent's ``lookup_bedrock`` tool answers from this file plus the
vendored Mojang schemas under ``portkit/validate/schemas``. It is generated, not
hand-edited: this script fetches a handful of files from two upstream repos at
the pinned commits below, cuts each down to a minimal example, and writes one
JSON file with sorted keys so a regeneration at the same pins is byte-identical.

Sources (see reference/NOTICE.md for licences and attribution):

- Mojang/bedrock-samples: vanilla pack files, used for small real examples
  (a recipe, a loot table, a few entries from the texture and sound indexes).
- MicrosoftDocs/minecraft-creator: the Bedrock reference docs (CC-BY-4.0,
  code samples MIT), used for property tables, one-line summaries, tag lists and
  component snippets.

The notes are portkit's own: what the validator checks and the mistakes the
residue agent makes.

Usage:
    python scripts/build_bedrock_reference.py [--cache DIR] [--check]

``--check`` rebuilds in memory and exits 1 if the committed file differs.
Network access is needed unless every file is already in ``--cache``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "portkit" / "agent" / "reference" / "bedrock_reference.json"
SCHEMAS = ROOT / "src" / "portkit" / "validate" / "schemas" / "1.26.60"

PINS = {
    "samples": ("Mojang/bedrock-samples", "46ba6ea985fb5a92d79a9419198f10dda14c199d"),
    "docs": ("MicrosoftDocs/minecraft-creator", "4186dc4ec84c8980fc25d89c26e1414aa6c2fde2"),
}
DOCS = "creator/Reference/Content"
BLOCK_DOCS = f"{DOCS}/BlockReference/Examples/BlockComponents"
ITEM_DOCS = f"{DOCS}/ItemReference/Examples/ItemComponents"
RECIPE_DOCS = f"{DOCS}/RecipeReference/Examples/RecipeDefinitions"

MAX_EXAMPLE = 1400
MAX_FIELDS = 40
MAX_FIELD_CHARS = 180
MAX_SUMMARY = 320
MAX_BYTES = 400_000  # the whole reference file; well under the ~1 MB budget

# ---------------------------------------------------------------- notes
# Hand-written, portkit's own. Keep each to a few sentences.
NOTES = {
    "block": (
        "One file per block in behavior_pack/blocks/<name>.json. The identifier must be "
        "<namespace>:<name>, never minecraft:. menu_category.category is one of construction, "
        "nature, equipment, items, none. A block needs at least one component; unknown "
        "minecraft: component names are a validator error, so look a component up before using it."
    ),
    "item": (
        "One file per item in behavior_pack/items/<name>.json, format_version 1.20.20 or later "
        "for the current component system. The example is vanilla: use your own namespace. "
        "minecraft:icon names a key in resource_pack/textures/item_texture.json, not a file path."
    ),
    "blocks.json": (
        "resource_pack/blocks.json maps a block identifier to its sound and textures. textures is "
        "one terrain_texture.json key, or an object per face (up, down, side, or north/south/east/west). "
        "Custom blocks with minecraft:material_instances get textures there instead; keep sound here. "
        "Custom entries use the full identifier, e.g. \"demo:die\"."
    ),
    "terrain_texture.json": (
        "resource_pack/textures/terrain_texture.json: texture_data maps a shortname to a path "
        "relative to the pack root, without .png. portkit's validator wants every key namespaced, "
        "<namespace>:<name> (e.g. examplemod:steel_block; vanilla's own keys have no namespace), "
        "and every path to exist as a .png. material_instances and blocks.json refer to these keys."
    ),
    "item_texture.json": (
        "resource_pack/textures/item_texture.json: same shape as terrain_texture.json with "
        "texture_name atlas.items. minecraft:icon on an item names one of these keys. Keys are "
        "namespaced (<namespace>:<name>) for portkit's validator; paths are relative to the pack "
        "root and have no .png extension."
    ),
    "flipbook_textures.json": (
        "resource_pack/textures/flipbook_textures.json is a JSON list. Each entry needs "
        "flipbook_texture (path without .png, must exist), atlas_tile (a key already in "
        "terrain_texture.json or item_texture.json) and ticks_per_frame (positive integer). "
        "The frames are stacked vertically in one PNG."
    ),
    "lang": (
        "resource_pack/texts/<Locale>.lang is key=value, one per line; # starts a comment. "
        "Blocks are tile.<namespace>:<name>.name and items item.<namespace>:<name>.name, the keys "
        "portkit's lang converter writes (the docs also show item keys without .name; "
        "minecraft:display_name can point at any key). A line break inside a value "
        "is written ~LINEBREAK~, never a real newline. Add entries with set_lang_entries rather "
        "than rewriting the file, and list the locale in texts/languages.json."
    ),
    "languages.json": (
        "resource_pack/texts/languages.json lists the locales the pack ships, e.g. [\"en_US\"]. "
        "set_lang_entries adds the locale for you. Bedrock ignores a .lang file for a locale outside "
        "its fixed list."
    ),
    "sound_definitions.json": (
        "resource_pack/sounds/sound_definitions.json maps a sound event name to the files it plays. "
        "Paths are relative to the pack root without extension (.ogg or .wav). category is one of "
        "ambient, block, hostile, music, neutral, player, record, ui, weather."
    ),
    "sounds.json": (
        "resource_pack/sounds.json binds events (break, place, hit, step) on blocks, entities and "
        "items to names from sound_definitions.json. For a custom block, setting \"sound\" in "
        "blocks.json to a vanilla sound type (stone, wood, metal, ...) is usually enough."
    ),
    "loot_table": (
        "behavior_pack/loot_tables/<path>.json, referenced from minecraft:loot as "
        "\"loot_tables/blocks/<name>.json\". portkit's validator wants at least one pool, numeric "
        "rolls, entries of type item with a namespaced name, and only these functions: set_count "
        "(numeric count), explosion_decay, set_data, looting_enchant."
    ),
    "recipe_shaped": (
        "behavior_pack/recipes/<name>.json. description.identifier must be lowercase "
        "<namespace>:<name>. Every pattern row must be the same width (pad with "
        "spaces); every character in the pattern needs a key entry and every key must be used. "
        "A key entry is {\"item\": id} or {\"tag\": \"minecraft:planks\"}. tags names the station: "
        "crafting_table, stonecutter, ... . result is {\"item\": id, \"count\": n}."
    ),
    "recipe_shapeless": (
        "ingredients is a non-empty list of {\"item\": id} or {\"tag\": t}, optionally with count; "
        "result is {\"item\": id, \"count\": n}. The data field is deprecated since 1.20 and the "
        "vanilla example still carries it; omit it in new files. Needs at least one tag, e.g. "
        "crafting_table."
    ),
    "recipe_furnace": (
        "input and output are item identifier strings (output, not result). tags lists every "
        "station that can cook it: furnace, blast_furnace, smoker, campfire, soul_campfire."
    ),
    "recipe_smithing_transform": (
        "template, base, addition and result are all required item identifiers; tags is "
        "[\"smithing_table\"]. Java's smithing_transform maps one to one. A Java smithing recipe "
        "missing any of the three inputs has no Bedrock form."
    ),
    "recipe_smithing_trim": (
        "Armour trims: template, base and addition (item ids or {\"tag\": ...}); there is no "
        "result because the base item keeps its identity. tags is [\"smithing_table\"]. Custom "
        "trim patterns and materials need more than a recipe, so a Java trim recipe for a new "
        "pattern usually stays residue."
    ),
    "recipe_brewing_mix": (
        "Brewing stand recipe: input and output are potion types (minecraft:potion_type:<name>), "
        "reagent is an item. tags is [\"brewing_stand\"]."
    ),
    "recipe_item_tags": (
        "Item tags a recipe ingredient can name as {\"tag\": \"minecraft:planks\"} instead of one item. "
        "Java item tags with the same meaning map to these; a Java tag with no Bedrock equivalent "
        "has to be expanded into explicit items or separate recipes."
    ),
    "item_tags": (
        "Vanilla item tags for the item component minecraft:tags. Only vanilla tags may use the "
        "minecraft: namespace; custom tags use your own."
    ),
    "block_tags": (
        "Vanilla block tags for the block component minecraft:tags. Older ones have no namespace. "
        "Mining-speed tags such as stone_pick_diggable affect which tools break the block fast."
    ),
    "minecraft:destructible_by_mining": (
        "Replaces Java hardness. seconds_to_destroy is roughly Java hardness x 1.5 for a hand; a "
        "negative value makes the block unbreakable. true/false is also accepted."
    ),
    "minecraft:destructible_by_explosion": (
        "Replaces Java blast resistance: explosion_resistance. false makes it immune."
    ),
    "minecraft:geometry": (
        "A string id (minecraft:geometry.full_block, minecraft:geometry.cross) or an object with "
        "identifier plus optional bone_visibility. A custom id needs a matching "
        "resource_pack/models/blocks/<name>.geo.json."
    ),
    "minecraft:material_instances": (
        "Per-face textures: keys are * (all faces), up, down, north, south, east, west or a bone's "
        "material name. texture is a terrain_texture.json key (validator checks it resolves). "
        "render_method: opaque, alpha_test, blend, double_sided."
    ),
    "minecraft:loot": "Path to a loot table relative to the behavior pack, e.g. \"loot_tables/blocks/steel_block.json\".",
    "minecraft:display_name": (
        "A lang key (tile.<namespace>:<name>.name) or literal text. Without it the game uses "
        "tile.<identifier>.name from the .lang files."
    ),
    "minecraft:light_emission": "Integer 0-15, Java's luminance.",
    "minecraft:map_color": "Hex string \"#RRGGBB\" or [r, g, b].",
    "minecraft:collision_box": "true, false, or {origin: [x,y,z], size: [x,y,z]} in pixels (block = 16), origin from the bottom centre.",
    "minecraft:tags": "Block tags as a list of strings, e.g. [\"stone\", \"minecraft:is_pickaxe_item_destructible\"]. See block_tags.",
    "item:minecraft:icon": (
        "Names a key in resource_pack/textures/item_texture.json, as a string or "
        "{\"textures\": {\"default\": key}}. The single \"texture\" field is deprecated."
    ),
    "item:minecraft:tags": "{\"tags\": [...]} with vanilla (minecraft:) or your own namespaced tags. See item_tags.",
    "item:minecraft:max_stack_size": "Integer 1-64, or {\"value\": n}.",
    "item:minecraft:durability": "max_durability is Java's maxDamage.",
}

# Topics beyond the block components the schema lists. Each one is a dict:
#   kind, aliases, schema (a vendored schema path, optional),
#   fields (docs page with property tables), summary (docs page), example spec.
# Example specs:
#   ("samples", path)                     the whole file
#   ("samples", path, {"keys": [...]})    keep these top-level keys only
#   ("samples", path, {"pick": key, "keys": [...]}) keep these keys of obj[pick]
#   ("samples", path, {"items": [...]})   keep list entries whose atlas_tile matches
#   ("samples", path, {"lines": [...]})   .lang lines whose key matches
#   ("docs", path, n)                     the n-th ```json block
FILE_TOPICS = {
    "block": {
        "kind": "document",
        "aliases": ["block.json", "minecraft:block", "behavior_pack/blocks"],
        "schema": "bp/blocks/index.schema.json",
        "example": ("docs", "creator/Documents/AddCustomDieBlock.md", 5),
    },
    "item": {
        "kind": "document",
        "aliases": ["item.json", "minecraft:item", "behavior_pack/items"],
        "schema": "bp/items/index.schema.json",
        "example": ("samples", "behavior_pack/items/apple.json"),
    },
    "blocks.json": {
        "kind": "file",
        "aliases": ["resource_pack/blocks.json"],
        "example": ("samples", "resource_pack/blocks.json", {"keys": ["stone", "oak_log", "crafting_table"]}),
    },
    "terrain_texture.json": {
        "kind": "file",
        "aliases": ["terrain_texture", "textures/terrain_texture.json", "atlas.terrain"],
        "example": (
            "samples", "resource_pack/textures/terrain_texture.json",
            {"pick": "texture_data", "keys": ["crafting_table_top", "stone"]},
        ),
    },
    "item_texture.json": {
        "kind": "file",
        "aliases": ["item_texture", "textures/item_texture.json", "atlas.items"],
        "example": (
            "samples", "resource_pack/textures/item_texture.json",
            {"pick": "texture_data", "keys": ["apple", "diamond_sword"]},
        ),
    },
    "flipbook_textures.json": {
        "kind": "file",
        "aliases": ["flipbook", "flipbook_textures", "textures/flipbook_textures.json", "texture_animation"],
        "example": ("samples", "resource_pack/textures/flipbook_textures.json", {"items": ["sea_lantern"]}),
    },
    "lang": {
        "kind": "file",
        "aliases": [".lang", "en_us.lang", "texts", "~linebreak~", "linebreak", "lang_file", "translation"],
        "example": (
            "samples", "resource_pack/texts/en_US.lang",
            {"lines": ["tile.dirt_with_roots.name", "item.apple.name", "item.diamond_sword.name",
                       "gameTip.cameraMovement.mouse"]},
        ),
    },
    "languages.json": {
        "kind": "file",
        "aliases": ["texts/languages.json"],
        "example": ("samples", "resource_pack/texts/languages.json"),
    },
    "sound_definitions.json": {
        "kind": "file",
        "aliases": ["sound_definitions", "sounds/sound_definitions.json"],
        "example": (
            "samples", "resource_pack/sounds/sound_definitions.json",
            {"pick": "sound_definitions", "keys": ["dig.stone"], "keep": ["format_version"]},
        ),
    },
    "sounds.json": {
        "kind": "file",
        "aliases": ["resource_pack/sounds.json", "block_sounds"],
        "example": ("samples", "resource_pack/sounds.json", {"pick": "block_sounds", "keys": ["stone"]}),
    },
    "loot_table": {
        "kind": "file",
        "aliases": ["loot", "loot_tables", "minecraft:loot_table"],
        "fields": f"{DOCS}/LootTableReference/Examples/LootTableComponents/loot_table.md",
        "example": ("samples", "behavior_pack/loot_tables/blocks/black_wool_slab.json"),
    },
    "recipe_shaped": {
        "kind": "recipe",
        "aliases": ["minecraft:recipe_shaped", "shaped", "crafting_shaped"],
        "fields": f"{RECIPE_DOCS}/recipe_shaped.md",
        "example": ("samples", "behavior_pack/recipes/brewing_stand.json"),
    },
    "recipe_shapeless": {
        "kind": "recipe",
        "aliases": ["minecraft:recipe_shapeless", "shapeless", "crafting_shapeless"],
        "fields": f"{RECIPE_DOCS}/recipe_shapeless.md",
        "example": ("samples", "behavior_pack/recipes/flint_and_steel.json"),
    },
    "recipe_furnace": {
        "kind": "recipe",
        "aliases": ["minecraft:recipe_furnace", "furnace", "smelting", "blasting", "smoking", "campfire_cooking"],
        "fields": f"{RECIPE_DOCS}/recipe_furnace.md",
        "example": ("samples", "behavior_pack/recipes/furnace_iron.json"),
    },
    "recipe_smithing_transform": {
        "kind": "recipe",
        "aliases": ["minecraft:recipe_smithing_transform", "smithing_transform", "smithing"],
        "fields": f"{RECIPE_DOCS}/recipe_smithing_transform.md",
        "example": ("samples", "behavior_pack/recipes/smithing_netherite_axe.json"),
    },
    "recipe_smithing_trim": {
        "kind": "recipe",
        "aliases": ["minecraft:recipe_smithing_trim", "smithing_trim", "armor_trim", "trim"],
        "fields": f"{RECIPE_DOCS}/recipe_smithing_trim.md",
        "example": ("samples", "behavior_pack/recipes/smithing_armor_trim.json"),
    },
    "recipe_brewing_mix": {
        "kind": "recipe",
        "aliases": ["minecraft:recipe_brewing_mix", "brewing", "brewing_mix"],
        "fields": f"{RECIPE_DOCS}/recipe_brewing_mix.md",
        "example": ("samples", "behavior_pack/recipes/brew_awkward_blaze_powder.json"),
    },
    "recipe_item_tags": {
        "kind": "tags",
        "aliases": ["recipe_tags", "tag_input", "recipe_tag_input"],
        "tags": f"{RECIPE_DOCS}/RecipeTagList.md",
    },
    "item_tags": {
        "kind": "tags",
        "aliases": ["vanilla_item_tags"],
        "tags": f"{DOCS}/ItemReference/Examples/vanilla-item-tags.md",
    },
    "block_tags": {
        "kind": "tags",
        "aliases": ["vanilla_block_tags"],
        "tags": f"{DOCS}/BlockReference/Examples/VanillaBlockTags.md",
    },
}

# Item components worth having for residue (the docs list ~55). No vendored
# schema covers item components, so these carry the docs' property tables.
ITEM_COMPONENTS = [
    "allow_off_hand", "block_placer", "cooldown", "damage", "digger", "display_name",
    "durability", "enchantable", "fire_resistant", "food", "fuel", "glint", "hand_equipped",
    "icon", "max_stack_size", "rarity", "repairable", "tags", "use_animation",
    "use_modifiers", "wearable",
]

# Block components whose docs page is named differently from the component.
BLOCK_DOC_NAMES = {"tags": "tag"}


# ---------------------------------------------------------------- fetching
def fetch(repo: str, path: str, cache: Path) -> str | None:
    slug, sha = PINS[repo]
    target = cache / repo / sha / path
    if target.is_file():
        return target.read_text(encoding="utf-8")
    missing = target.with_name(target.name + ".404")
    if missing.is_file():
        return None
    url = f"https://raw.githubusercontent.com/{slug}/{sha}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            missing.parent.mkdir(parents=True, exist_ok=True)
            missing.write_text("")
            return None
        raise
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return text


def source_id(repo: str, path: str) -> str:
    slug, sha = PINS[repo]
    return f"{slug}@{sha[:12]}:{path}"


# ---------------------------------------------------------------- parsing
def loads_vanilla(text: str):
    """Vanilla files open with // comment lines; strip them."""
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))
    return json.loads(body)


def dump(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def cap(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def sample_example(text: str, spec: dict | None) -> str:
    if spec and "lines" in spec:
        wanted = spec["lines"]
        lines = {l.split("=", 1)[0]: l for l in text.splitlines() if "=" in l}
        return "\n".join(lines[k] for k in wanted if k in lines)
    data = loads_vanilla(text)
    if not spec:
        return dump(data)
    if "items" in spec:
        return dump([e for e in data if e.get("atlas_tile") in spec["items"]][:1])
    if "pick" in spec:
        inner = data[spec["pick"]]
        out = {k: v for k, v in data.items() if k != spec["pick"] and (
            not isinstance(v, (dict, list)) or k in spec.get("keep", []))}
        out[spec["pick"]] = {k: inner[k] for k in spec["keys"] if k in inner}
        return dump(out)
    return dump({k: data[k] for k in spec["keys"] if k in data})


_CODE = re.compile(r"```(\w*)\n(.*?)```", re.S)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def tidy_snippet(body: str) -> str:
    """Re-indent a docs code block when it parses, as a document or as the
    ``"key": value`` fragment most component pages show; else strip trailing space."""
    try:
        return dump(json.loads(body))
    except ValueError:
        pass
    try:
        fragment = json.loads("{" + body.strip().rstrip(",") + "}")
    except ValueError:
        return "\n".join(line.rstrip() for line in body.strip().splitlines())
    return ",\n".join(f"{json.dumps(k)}: {dump(v)}" for k, v in fragment.items())


def docs_blocks(text: str) -> list[str]:
    return [tidy_snippet(body) for lang, body in _CODE.findall(text) if lang.lower() in ("json", "jsonc", "")]


def docs_summary(text: str) -> str:
    """The first prose paragraph after the H1."""
    body = text.split("\n---\n", 1)[-1] if text.startswith("---") else text
    after = body.split("\n# ", 1)[-1].split("\n", 1)[-1]
    for para in re.split(r"\n\s*\n", after):
        para = para.strip()
        if para and not para.startswith(("#", ">", "|", "!", "```", "-", "*")):
            return cap(_LINK.sub(r"\1", " ".join(para.split())), MAX_SUMMARY)
    return ""


def docs_fields(text: str) -> list[str]:
    """Property tables as 'path.name (type, default): description' lines."""
    out: list[str] = []
    path = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"\*\*JSON path:\*\*\s*`([^`]*)`", line)
        if m:
            path = ".".join(p.strip() for p in m.group(1).split(">"))
        if line.startswith("|Name") or line.startswith("| Name"):
            header = [h.strip().lower() for h in line.strip("|").split("|")]
            i += 2  # skip the separator row
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                row = dict(zip(header, cells))
                name = row.get("name", "")
                if name:
                    typ = _LINK.sub(r"\1", row.get("type", "")).strip()
                    default = row.get("default value", "")
                    desc = _LINK.sub(r"\1", row.get("description", ""))
                    where = f"{path}.{name}" if path else name
                    dflt = f", default {default}" if default and "not set" not in default else ""
                    out.append(cap(f"{where} ({typ}{dflt}): {desc}".replace("  ", " "), MAX_FIELD_CHARS))
                i += 1
            continue
        i += 1
    return out[:MAX_FIELDS]


def docs_tags(text: str) -> list[str]:
    seen: list[str] = []
    for name in re.findall(r'"((?:minecraft:)?[a-z0-9_\\]+)"', text):
        name = name.replace("\\", "")
        if name not in seen:
            seen.append(name)
    return seen


# ---------------------------------------------------------------- build
def build(cache: Path) -> dict:
    topics: dict[str, dict] = {}

    def example_from(spec) -> tuple[str, str]:
        repo, path = spec[0], spec[1]
        text = fetch(repo, path, cache)
        if text is None:
            raise SystemExit(f"missing upstream file {repo}:{path}")
        if repo == "docs":
            return cap(docs_blocks(text)[spec[2]], MAX_EXAMPLE), source_id(repo, path)
        return cap(sample_example(text, spec[2] if len(spec) > 2 else None), MAX_EXAMPLE), source_id(repo, path)

    for name, spec in FILE_TOPICS.items():
        entry: dict = {"kind": spec["kind"], "aliases": sorted(spec.get("aliases", []))}
        sources: list[str] = []
        if "schema" in spec:
            entry["schema"] = spec["schema"]
        if "fields" in spec:
            text = fetch("docs", spec["fields"], cache)
            entry["summary"] = docs_summary(text)
            entry["fields"] = docs_fields(text)
            sources.append(source_id("docs", spec["fields"]))
        if "tags" in spec:
            text = fetch("docs", spec["tags"], cache)
            entry["summary"] = docs_summary(text)
            entry["tags"] = docs_tags(text)
            sources.append(source_id("docs", spec["tags"]))
        if "example" in spec:
            entry["example"], src = example_from(spec["example"])
            sources.append(src)
        entry["sources"] = sources
        topics[name] = entry

    components = json.loads((SCHEMAS / "bp/blocks/block_components.schema.json").read_text())["properties"]
    for comp in sorted(components):
        short = comp.split(":", 1)[1]
        entry = {"kind": "block_component", "aliases": sorted({short, f"block:{comp}", f"block:{short}"}),
                 "schema": f"bp/blocks/block_components.schema.json#/properties/{comp}", "sources": []}
        doc = f"{BLOCK_DOCS}/minecraftBlock_{BLOCK_DOC_NAMES.get(short, short)}.md"
        text = fetch("docs", doc, cache)
        if text is not None:
            entry["summary"] = docs_summary(text)
            blocks = docs_blocks(text)
            if blocks:
                entry["example"] = cap(blocks[0], MAX_EXAMPLE)
            entry["sources"].append(source_id("docs", doc))
        topics[comp] = entry

    for short in ITEM_COMPONENTS:
        name = f"item:minecraft:{short}"
        doc = f"{ITEM_DOCS}/minecraft_{short}.md"
        text = fetch("docs", doc, cache)
        if text is None:
            raise SystemExit(f"missing item component doc {doc}")
        entry = {"kind": "item_component", "aliases": sorted({f"item:{short}"}),
                 "summary": docs_summary(text), "fields": docs_fields(text),
                 "sources": [source_id("docs", doc)]}
        blocks = docs_blocks(text)
        if blocks:
            entry["example"] = cap(blocks[0], MAX_EXAMPLE)
        topics[name] = entry

    for name, note in NOTES.items():
        if name not in topics:
            raise SystemExit(f"note for unknown topic {name}")
        topics[name]["note"] = note

    return {
        "about": "Generated by scripts/build_bedrock_reference.py; do not edit by hand. See NOTICE.md.",
        "pins": {repo: {"repo": slug, "commit": sha} for repo, (slug, sha) in sorted(PINS.items())},
        "schema_snapshot": "1.26.60",
        "topics": topics,
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", default=str(ROOT / ".cache" / "bedrock-reference"))
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    args = parser.parse_args()
    text = render(build(Path(args.cache)))
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        print(f"reference is {size:,} bytes, over the {MAX_BYTES:,} cap", file=sys.stderr)
        return 1
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(ROOT)} is stale; rerun this script", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(ROOT)} is up to date ({size:,} bytes)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(json.loads(text)['topics'])} topics, {size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
