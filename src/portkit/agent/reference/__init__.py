"""Deterministic Bedrock reference for the residue agent (#114).

``lookup_bedrock(topic)`` answers "how is this spelled in Bedrock?" for a block
or item component, a recipe type, or a pack file (``terrain_texture.json``,
``.lang``, ...): the schema fragment from the vendored Mojang schemas, a short
real example, the docs' property table and a note on what portkit's validator
checks. ``list_bedrock_topics(prefix)`` lists what it knows.

No embeddings, no ranking model, no network: the answer is a pure function of
the topic string and two committed files (``bedrock_reference.json`` here, built
by ``scripts/build_bedrock_reference.py`` from pinned upstream commits, and the
schemas under ``portkit/validate/schemas``). The same call gives the same bytes
every time, so a recorded transcript that used it still replays.

Every answer is capped at :data:`MAX_CHARS` characters. An unknown topic gets
the closest known names, in a fixed order.
"""
from __future__ import annotations

import difflib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...validate.schema import SCHEMA_ROOT

REFERENCE_FILE = Path(__file__).with_name("bedrock_reference.json")
MAX_CHARS = 6000
MAX_SCHEMA_CHARS = 2500
MAX_SUGGESTIONS = 8
MAX_LISTED = 200

# Schema keys that are editor sugar or noise for the agent.
_DROP = {"defaultSnippets", "$schema", "$id", "title", "markdownDescription", "examples"}
_MAX_DESCRIPTION = 200

# Cross-references worth following from a topic, beyond same-named components.
_RELATED = {
    "minecraft:tags": ["block_tags"],
    "item:minecraft:tags": ["item_tags"],
    "minecraft:material_instances": ["terrain_texture.json", "blocks.json"],
    "minecraft:geometry": ["minecraft:material_instances"],
    "minecraft:loot": ["loot_table"],
    "minecraft:display_name": ["lang"],
    "item:minecraft:display_name": ["lang"],
    "item:minecraft:icon": ["item_texture.json"],
    "terrain_texture.json": ["minecraft:material_instances", "blocks.json", "flipbook_textures.json"],
    "item_texture.json": ["item:minecraft:icon"],
    "flipbook_textures.json": ["terrain_texture.json"],
    "lang": ["languages.json", "minecraft:display_name"],
    "languages.json": ["lang"],
    "loot_table": ["minecraft:loot"],
    "recipe_shaped": ["recipe_item_tags", "recipe_shapeless"],
    "recipe_shapeless": ["recipe_item_tags", "recipe_shaped"],
    "recipe_smithing_transform": ["recipe_smithing_trim"],
    "recipe_smithing_trim": ["recipe_smithing_transform"],
    "sound_definitions.json": ["sounds.json"],
    "sounds.json": ["sound_definitions.json", "blocks.json"],
    "blocks.json": ["terrain_texture.json", "sounds.json"],
    "block": ["blocks.json", "minecraft:material_instances"],
    "item": ["item:minecraft:icon", "item_texture.json"],
}


def _normalise(text: Any) -> str:
    return str(text if text is not None else "").strip().strip("'\"`").strip().lower().replace("\\", "/")


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    return json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    """Every name a topic answers to, lowercased, mapped to its canonical name.

    Canonical names are registered first, then aliases in sorted topic order, so
    when two topics claim one alias (``display_name`` is a block and an item
    component) the first in that order wins, and always the same one.
    """
    topics = _load()["topics"]
    table: dict[str, str] = {}
    for name in sorted(topics):
        table.setdefault(name.lower(), name)
    for name in sorted(topics):
        for alias in topics[name].get("aliases", []):
            table.setdefault(alias.lower(), name)
    return table


def topics() -> list[str]:
    return sorted(_load()["topics"])


def _schema_root() -> Path:
    return SCHEMA_ROOT / _load()["schema_snapshot"]


@lru_cache(maxsize=None)
def _schema_file(rel: str) -> Any:
    path = _schema_root() / rel
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pointer(doc: Any, pointer: str) -> Any:
    node = doc
    for part in [p for p in pointer.split("/") if p]:
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _compact(node: Any, file_rel: str, depth: int) -> Any:
    """A schema node with editor sugar dropped and ``$ref`` inlined ``depth`` deep."""
    if isinstance(node, list):
        return [_compact(v, file_rel, depth) for v in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    ref = node.get("$ref")
    if isinstance(ref, str):
        target_rel, _, frag = ref.partition("#")
        rel = str((Path(file_rel).parent / target_rel)) if target_rel else file_rel
        rel = str(Path(rel).as_posix())
        # normalise ./ and ../ without touching the filesystem
        parts: list[str] = []
        for p in rel.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(p)
        rel = "/".join(parts)
        doc = _schema_file(rel)
        target = _pointer(doc, frag) if doc is not None else None
        if target is not None and depth > 0:
            out.update(_compact(target, rel, depth - 1))
        else:
            out["$ref"] = Path(rel).name + (f"#{frag}" if frag else "")
    for key, value in node.items():
        if key in _DROP or key == "$ref":
            continue
        if key == "description" and isinstance(value, str):
            text = value.split("\n\nProperties:")[0].strip()
            if len(text) > _MAX_DESCRIPTION:
                text = text[: _MAX_DESCRIPTION - 3].rstrip() + "..."
            if text:
                out[key] = text
            continue
        out[key] = _compact(value, file_rel, depth)
    return out


def schema_fragment(ref: str) -> str:
    """The vendored schema at ``file#/pointer``, compacted to fit the schema budget."""
    rel, _, frag = ref.partition("#")
    doc = _schema_file(rel)
    node = _pointer(doc, frag) if doc is not None else None
    if node is None:
        return ""
    for depth in (2, 1, 0):
        text = json.dumps(_compact(node, rel, depth), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(text) <= MAX_SCHEMA_CHARS:
            return text
    return text[: MAX_SCHEMA_CHARS - 3] + "..."


def _resolve(query: str) -> str | None:
    table = _aliases()
    if query in table:
        return table[query]
    # A path: try the file name, then the name without .json.
    base = query.rsplit("/", 1)[-1]
    for candidate in (base, base.removesuffix(".json")):
        if candidate in table:
            return table[candidate]
    if base.endswith(".lang"):
        return table.get(".lang")
    if not query.startswith(("minecraft:", "item:", "block:")) and f"minecraft:{query}" in table:
        return table[f"minecraft:{query}"]
    return None


def suggestions(query: str) -> list[str]:
    """Closest known topics, deterministic: substring hits first (shortest, then
    alphabetical), then by difflib similarity (highest, then alphabetical).
    Empty when nothing is close; the caller points at list_bedrock_topics."""
    table = _aliases()
    picked: list[str] = []

    def add(name: str) -> None:
        if name not in picked:
            picked.append(name)

    if query:
        bare = query.split(":")[-1]
        hits = sorted({table[a] for a in table if query in a or (len(bare) >= 3 and bare in a)},
                      key=lambda n: (len(n), n))
        for name in hits:
            add(name)
        scored = sorted(
            ((difflib.SequenceMatcher(None, query, a).ratio(), table[a]) for a in sorted(table)),
            key=lambda pair: (-pair[0], pair[1]),
        )
        for ratio, name in scored:
            if ratio < 0.5 or len(picked) >= MAX_SUGGESTIONS:
                break
            add(name)
    return picked[:MAX_SUGGESTIONS]


def _see_also(name: str) -> list[str]:
    known = set(_load()["topics"])
    short = name.split(":")[-1]
    out = [n for n in _RELATED.get(name, []) if n in known]
    for other in (f"minecraft:{short}", f"item:minecraft:{short}"):
        if other != name and other in known and other not in out:
            out.append(other)
    return out


def _size(result: dict) -> int:
    return len(json.dumps(result, ensure_ascii=False))


def _fit(result: dict) -> dict:
    """Trim the longest parts until the answer fits in MAX_CHARS.

    Lists lose entries from the end first, then the long strings are cut, in a
    fixed order. Sizes are measured on the encoded answer, escapes included, and
    every step is a pure function of the input, so trimming is deterministic.
    """
    if _size(result) <= MAX_CHARS:
        return result
    result["truncated"] = True
    for key in ("fields", "tags"):
        items = result.get(key)
        while items and _size(result) > MAX_CHARS:
            items.pop()
            result[f"{key}_omitted"] = result.get(f"{key}_omitted", 0) + 1
    for key in ("example", "schema", "summary", "note"):
        while result.get(key) and _size(result) > MAX_CHARS:
            text = result[key].removesuffix("...")
            over = _size(result) - MAX_CHARS
            keep = max(0, len(text) - max(over, 16) - 3)
            result[key] = text[:keep].rstrip() + "..." if keep else ""
    return result


def lookup(topic: Any) -> dict[str, Any]:
    query = _normalise(topic)
    if not query:
        return {"error": "topic is empty", "hint": "call list_bedrock_topics to see what is known"}
    name = _resolve(query)
    if name is None:
        return {
            "error": f"unknown topic {query!r}",
            "did_you_mean": suggestions(query),
            "hint": "call list_bedrock_topics(prefix) for the full list",
        }
    entry = _load()["topics"][name]
    result: dict[str, Any] = {"topic": name, "kind": entry["kind"]}
    for key in ("summary", "note"):
        if entry.get(key):
            result[key] = entry[key]
    sources: list[str] = []
    if entry.get("schema"):
        fragment = schema_fragment(entry["schema"])
        if fragment:
            result["schema"] = fragment
            sources.append(f"Mojang/bedrock-schemas {_load()['schema_snapshot']} (vendored): {entry['schema']}")
    for key in ("fields", "tags"):
        if entry.get(key):
            result[key] = list(entry[key])
    if entry.get("example"):
        result["example"] = entry["example"]
    see_also = _see_also(name)
    if see_also:
        result["see_also"] = see_also
    result["sources"] = sources + list(entry.get("sources", []))
    return _fit(result)


def list_topics(prefix: Any = "") -> dict[str, Any]:
    query = _normalise(prefix)
    names = [
        n for n in topics()
        if not query or n.lower().startswith(query) or n.split(":")[-1].lower().startswith(query)
        or n.lower().startswith(f"minecraft:{query}")
    ]
    kinds = _load()["topics"]
    by_kind: dict[str, list[str]] = {}
    for n in names[:MAX_LISTED]:
        by_kind.setdefault(kinds[n]["kind"], []).append(n)
    result: dict[str, Any] = {"count": len(names), "topics": by_kind}
    if len(names) > MAX_LISTED:
        result["omitted"] = len(names) - MAX_LISTED
    if not names:
        result["did_you_mean"] = suggestions(query)
    return result
