"""Structural validation against Mojang's vendored Bedrock JSON schemas (#15).

The hand-written rules in ``rules.py`` keep the semantic checks a schema can't
express. This module checks the shape of a file against Mojang's own schemas
(github.com/Mojang/bedrock-schemas, MIT), vendored per snapshot under
``schemas/<version>/`` and picked by the file's ``format_version``.

The validator is a small stdlib subset of JSON Schema draft-07: ``$ref``
(relative files and ``#/`` fragments), ``type``, ``enum``, ``const``,
``properties``, ``required``, ``items``, ``anyOf``/``oneOf``, ``allOf``,
``additionalProperties``. Every finding carries a JSON pointer.

What it reports:

- ``schema.unknown_component`` (error): a ``minecraft:`` component name on a
  block (base or permutation) that the schema doesn't define. Bedrock refuses
  the block, and the schema is the authoritative list. Names in another
  namespace are custom components and are left alone.
- ``schema.type`` / ``schema.required`` / ``schema.enum`` (warning): shape
  mismatches. Mojang's schemas are generated and occasionally looser or stricter
  than the game, so these advise rather than fail the tree. Promote a rule to an
  error once it has been checked against the game.

A schema ``$ref`` that points at a file the snapshot doesn't ship accepts
anything, since upstream references a few ``common/`` files it doesn't publish.

Adding a snapshot: copy ``schemas/bp/blocks`` and ``schemas/bp/items`` from a
bedrock-schemas release into ``schemas/<version>/bp/``, add the version to
``SNAPSHOTS``, and record the commit in ``schemas/SOURCE.md``.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .report import ValidationReport

SCHEMA_ROOT = Path(__file__).parent / "schemas"
# Vendored snapshots, oldest first. A file is checked against the oldest
# snapshot at or above its format_version, so the newest is the catch-all.
SNAPSHOTS: list[tuple[int, ...]] = [(1, 26, 60)]

_BLOCK_DOCUMENT = "bp/blocks/index.schema.json"
_BLOCK_COMPONENTS = "bp/blocks/block_components.schema.json"
_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _version(text: Any) -> tuple[int, ...] | None:
    try:
        return tuple(int(p) for p in str(text).split("."))
    except ValueError:
        return None


def snapshot_for(format_version: Any) -> Path:
    wanted = _version(format_version)
    if wanted is not None:
        for snap in SNAPSHOTS:
            if snap >= wanted:
                return SCHEMA_ROOT / ".".join(map(str, snap))
    return SCHEMA_ROOT / ".".join(map(str, SNAPSHOTS[-1]))


@lru_cache(maxsize=None)
def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def pointer(parts: list[str | int]) -> str:
    """RFC 6901 JSON pointer for a path of keys and indexes."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _is_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected = _TYPES.get(name)
    return expected is None or isinstance(value, expected)


class _Checker:
    def __init__(self, base: Path):
        self.base = base
        self.errors: list[tuple[str, str, str]] = []  # (rule, pointer, message)

    def resolve(self, schema: dict, here: Path) -> tuple[dict | None, Path]:
        ref = schema.get("$ref")
        if not isinstance(ref, str):
            return schema, here
        file_part, _, fragment = ref.partition("#")
        target = (here.parent / file_part).resolve() if file_part else here
        if not target.is_file():
            return None, here  # upstream points at a file it doesn't publish
        node: Any = _load(target)
        for key in [k for k in fragment.split("/") if k]:
            node = node.get(key) if isinstance(node, dict) else None
        return (node if isinstance(node, dict) else None), target

    def matches(self, value: Any, schema: dict, here: Path) -> bool:
        probe = _Checker(self.base)
        probe.check(value, schema, here, [])
        return not probe.errors

    def check(self, value: Any, schema: Any, here: Path, path: list) -> None:
        if not isinstance(schema, dict):
            return
        schema, here = self.resolve(schema, here)
        if schema is None:
            return
        where = pointer(path) or "/"

        types = schema.get("type")
        if types is not None:
            names = types if isinstance(types, list) else [types]
            if not any(_is_type(value, n) for n in names):
                self.errors.append(("schema.type", where, f"expected {' or '.join(names)}, got {type(value).__name__}"))
                return
        if "enum" in schema and value not in schema["enum"]:
            self.errors.append(("schema.enum", where, f"{value!r} is not one of {schema['enum']}"))
        if "const" in schema and value != schema["const"]:
            self.errors.append(("schema.enum", where, f"{value!r} is not {schema['const']!r}"))
        for sub in schema.get("allOf") or []:
            self.check(value, sub, here, path)
        for key in ("anyOf", "oneOf"):
            options = schema.get(key)
            if options and not any(self.matches(value, o, here) for o in options):
                self.errors.append(("schema.type", where, f"matches none of the {len(options)} allowed shapes"))

        if isinstance(value, dict):
            props = schema.get("properties") or {}
            for name in schema.get("required") or []:
                if name not in value:
                    self.errors.append(("schema.required", where, f"missing required property {name!r}"))
            extra = schema.get("additionalProperties")
            for name, child in value.items():
                if name in props:
                    self.check(child, props[name], here, [*path, name])
                elif extra is False:
                    self.errors.append(("schema.type", pointer([*path, name]), f"property {name!r} is not allowed here"))
                elif isinstance(extra, dict):
                    self.check(child, extra, here, [*path, name])
        elif isinstance(value, list) and isinstance(schema.get("items"), dict):
            for i, child in enumerate(value):
                self.check(child, schema["items"], here, [*path, i])


def known_block_components(snapshot: Path) -> set[str]:
    return set((_load(snapshot / _BLOCK_COMPONENTS).get("properties") or {}))


def check_block(report: ValidationReport, data: Any, rel: str) -> None:
    if not isinstance(data, dict):
        return
    snapshot = snapshot_for(data.get("format_version"))
    known = known_block_components(snapshot)
    block = data.get("minecraft:block")
    if isinstance(block, dict):
        groups: list[tuple[list, Any]] = [(["minecraft:block", "components"], block.get("components"))]
        for i, perm in enumerate(block.get("permutations") or []):
            if isinstance(perm, dict):
                groups.append((["minecraft:block", "permutations", i, "components"], perm.get("components")))
        for path, components in groups:
            if not isinstance(components, dict):
                continue
            for name in components:
                if name.startswith("minecraft:") and name not in known:
                    where = pointer([*path, name])
                    report.add(
                        rel,
                        "schema.unknown_component",
                        f"{where}: {name!r} is not a block component in the Bedrock {snapshot.name} schema",
                        pointer=where,
                    )
    checker = _Checker(snapshot)
    checker.check(data, _load(snapshot / _BLOCK_DOCUMENT), snapshot / _BLOCK_DOCUMENT, [])
    for rule, where, message in checker.errors:
        report.add(rel, rule, f"{where}: {message}", severity="warning", pointer=where)
