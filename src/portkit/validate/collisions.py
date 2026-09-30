"""Two things claiming one name.

Bedrock does not complain when two files declare the same identifier. It loads
one of them, drops the other, and the mod is quietly missing a block. That is
the wrong-but-valid failure this project exists to refuse, so it is an error
here and it names both files.

Shadowing a vanilla `minecraft:` name is the same problem wearing a different
hat: the pack loads, the vanilla thing wins or yours does depending on load
order, and nobody can tell you which.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .report import ValidationReport

# Where a definition keeps its name, per content type. The key is the wrapper
# Bedrock expects; recipes carry several and any one of them can hold the name.
_DEFINITION_KEYS = {
    "block": ("minecraft:block",),
    "item": ("minecraft:item",),
    "recipe": (
        "minecraft:recipe_shaped",
        "minecraft:recipe_shapeless",
        "minecraft:recipe_furnace",
        "minecraft:recipe_brewing_mix",
        "minecraft:recipe_brewing_container",
        "minecraft:recipe_smithing_transform",
    ),
}

# Directories that hold each kind, relative to a pack root.
_DIRECTORIES = {
    "block": "blocks",
    "item": "items",
    "recipe": "recipes",
}


def _identifier(data: dict, kind: str) -> str | None:
    for key in _DEFINITION_KEYS[kind]:
        body = data.get(key)
        if isinstance(body, dict):
            name = (body.get("description") or {}).get("identifier")
            if isinstance(name, str):
                return name
    return None


def _definitions(tree: Path) -> dict[tuple[str, str], list[str]]:
    """Every declared identifier in the tree, mapped to the files declaring it."""
    found: dict[tuple[str, str], list[str]] = defaultdict(list)
    for pack in ("behavior_pack", "resource_pack"):
        root = tree / pack
        if not root.is_dir():
            continue
        for kind, directory in _DIRECTORIES.items():
            for path in sorted((root / directory).glob("*.json")):
                try:
                    data = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue  # rules.py already reports unreadable JSON
                if not isinstance(data, dict):
                    continue
                name = _identifier(data, kind)
                if name:
                    rel = f"{pack}/{directory}/{path.name}"
                    found[(kind, name)].append(rel)
    return found


def check_collisions(report: ValidationReport, tree: Path) -> None:
    """Duplicate identifiers, and custom content squatting on a vanilla name."""
    definitions = _definitions(tree)

    for (kind, name), files in sorted(definitions.items()):
        if len(files) > 1:
            report.add(
                files[0],
                f"{kind}.identifier_collision",
                f"{name} is declared {len(files)} times: " + ", ".join(files),
            )
        if name.startswith("minecraft:"):
            report.add(
                files[0],
                f"{kind}.vanilla_shadow",
                f"{name} shadows a vanilla identifier; load order decides which one wins",
            )

    # A block and an item under one name is legal in Bedrock and common on
    # purpose (a block with its own item form), so it is worth saying out loud
    # without failing the pack.
    by_name: dict[str, set[str]] = defaultdict(set)
    files_by_name: dict[str, list[str]] = defaultdict(list)
    for (kind, name), files in definitions.items():
        by_name[name].add(kind)
        files_by_name[name].extend(files)
    for name, kinds in sorted(by_name.items()):
        if {"block", "item"} <= kinds:
            report.add(
                sorted(files_by_name[name])[0],
                "identifier.block_and_item",
                f"{name} is declared as both a block and an item; intended for a "
                "block with its own item form, a mistake otherwise",
                severity="warning",
            )
