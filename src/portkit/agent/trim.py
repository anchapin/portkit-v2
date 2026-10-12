"""Is the agent-written ``minecraft:recipe_smithing_trim`` something Bedrock can apply? (#86)

A Java ``minecraft:smithing_trim`` recipe names a *template* (the pattern), a
*base* (the armour being trimmed) and an *addition* (the material). Bedrock has
the same recipe shape and the structural oracle (``minecraft:recipe_smithing_trim``
in :mod:`portkit.validate.rules`) only checks that all three slots are
non-empty; it does not check that any of those items actually exist on Bedrock
or that the mod registered a trim definition the recipe depends on. So a model
that wrote

    {"minecraft:recipe_smithing_trim": {"template": {...}, "base": {...},
    "addition": {"item": "examplemod:steel_ingot"}}}

for an agent_mod trim, with the deterministic path's note still in the task,
got the group to ``resolved``: the file parsed, every required slot was
non-empty, the validator was clean. The trim did nothing in game, though,
because the addition is a mod item carrying neither ``minecraft:trim_materials``
nor a mod ``trim_material`` definition that Java would have applied before
ever reading the recipe.

So the residue agent holds its written trim recipes to a stricter, deterministic
rule, in the spirit of :mod:`portkit.agent.refs` and :mod:`portkit.agent.stats`:

- *Every* ``template`` and ``addition`` in a written ``minecraft:recipe_smithing_trim``
  must name a vanilla ``minecraft:`` item or tag, OR a non-vanilla id the source
  mod defines and for which the source ships a matching ``trim_pattern`` /
  ``trim_material`` definition (``data/<namespace>/trim_pattern/<id>.json``,
  ``data/<namespace>/trim_material/<id>.json``). ``base`` is not gated here: a
  trimmable armour item, vanilla or modded, is always accepted by Bedrock's
  recipe matcher, so a vanilla tag is the only meaningful choice and a modded
  base is fine if its modded form carries ``minecraft:trimmable_armors`` (a
  descriptive component, not a guardable one).

If a written trim violates the rule, :func:`finding` produces a
``agent.unresolved_trim`` validate error, and :func:`fabricated_trims` is the
list the residue agent rolls the group back for. Vanilla-only trims are taken
on faith for the same reason ``refs.py`` takes vanilla ids on faith (the comment
near :data:`VANILLA` in that module spells it out).

The check is aimed at what a model can invent: ids in the mod's own namespace,
or any other non-vanilla namespace, used as a trim template or trim material
without a registered definition. The vanilla-only path (Mojang's own trims)
is never gated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# ``refs.py`` keeps the same constant and the same reasoning. Repeated here so
# this module has no dependency on a sibling's internals.
_VANILLA = "minecraft"

# Slots the rule looks at. ``base`` is intentionally not listed; see the module
# docstring for why.
_TRIM_SLOTS: tuple[str, ...] = ("template", "addition")

# Files that say "this id is a real trim template / material the mod registered".
# Java requires these for the recipe to mean anything; Bedrock has no
# equivalent, and a recipe that names a mod id without one is a no-op.
_TRIM_DEFINITION_FOLDERS: dict[str, tuple[str, ...]] = {
    "template": ("trim_pattern",),
    "addition": ("trim_material",),
}


@dataclass(frozen=True)
class Trim:
    path: str  # the pack file that holds the recipe, relative to the output tree
    where: str  # "template" | "addition"
    ident: str

    def describe(self) -> str:
        return f"{self.path} {self.where}: {self.ident!r}"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _trim_bodies(out_tree: Path, rel: str) -> list[dict]:
    """Every ``minecraft:recipe_smithing_trim`` body one pack recipe file holds."""
    data = _load(out_tree / rel)
    if not isinstance(data, dict):
        return []
    bodies: list[dict] = []
    for top, body in data.items():
        if top == "minecraft:recipe_smithing_trim" and isinstance(body, dict):
            bodies.append(body)
    return bodies


def _trim_ident(spec) -> str | None:
    """The id a trim slot names, in either Bedrock shape."""
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        for key in ("item", "tag"):
            value = spec.get(key)
            if isinstance(value, str):
                return value
    return None


def _trim_definition_names(source_root: Path) -> set[str]:
    """Every ``<namespace>:<id>`` the source registers as a trim template or material.

    The mod's own ``trim_material/`` and ``trim_pattern/`` folders are the only
    thing Java's trim recipe reader consults to decide whether a trim recipe
    applies; nothing else in the mod tells Bedrock the same thing. The folder
    layout is fixed: ``data/<namespace>/trim_material/<id>.json`` (or
    ``trim_pattern``), so the namespace is two levels above the file.
    """
    found: set[str] = set()
    data_root = source_root / "data"
    if not data_root.is_dir():
        return found
    for folders in _TRIM_DEFINITION_FOLDERS.values():
        for folder in folders:
            for entry in sorted(data_root.rglob(f"{folder}/*.json")):
                # data/<ns>/<folder>/<id>.json -> ns is the first part, folder
                # the second, id is the file name without ``.json``.
                parts = entry.relative_to(data_root).parts
                if len(parts) != 3:
                    continue
                ns, leaf_folder, filename = parts
                if leaf_folder != folder or not filename.endswith(".json"):
                    continue
                found.add(f"{ns}:{filename[:-5]}")
    return found


def _is_trim_recipe(rel: str) -> bool:
    return rel.startswith("behavior_pack/recipes/") and rel.endswith(".json")


def fabricated_trims(out_tree: Path, written: list[str], source_root: Path) -> list[Trim]:
    """Trims the session wrote that name a template or addition with no working form.

    The result is a :class:`Trim` per offending slot; a single recipe can
    contribute up to two (one template, one addition). The rule is applied
    slot-by-slot: a vanilla slot passes, a mod-namespaced slot needs a
    matching ``trim_pattern``/``trim_material`` definition in the source.
    """
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    recipes = [rel for rel in normalised if _is_trim_recipe(rel) and (out_tree / rel).is_file()]
    if not recipes:
        return []
    mod_trims = _trim_definition_names(source_root)
    bad: list[Trim] = []
    for rel in recipes:
        for body in _trim_bodies(out_tree, rel):
            for slot in _TRIM_SLOTS:
                ident = _trim_ident(body.get(slot))
                if ident is None:
                    continue
                namespace, _, _ = ident.partition(":")
                if namespace == _VANILLA:
                    continue  # vanilla ids are taken on faith
                if ident in mod_trims:
                    continue
                bad.append(Trim(rel, slot, ident))
    return bad


def finding(trim: Trim) -> dict:
    """The validate-tool finding for one unresolved trim, as the agent sees it.

    Tells the agent the exact slot, the exact id, and why a written Bedrock
    recipe for it cannot apply anything: a non-vanilla trim template or trim
    material without a registered definition does nothing in game, so the
    honest answer is to write nothing and decline with a one-sentence reason.
    """
    folder = "trim_pattern" if trim.where == "template" else "trim_material"
    message = (
        f"{trim.where} names {trim.ident!r}, a non-vanilla trim "
        f"{'pattern' if trim.where == 'template' else 'material'}, but the mod ships no "
        f"data/<namespace>/{folder}/<id>.json definition for it. Bedrock's recipe_smithing_trim "
        "applies nothing for a trim slot that is neither vanilla nor registered. Write nothing "
        "and decline: say which slot lacks a working form and that the Java mod has to ship "
        f"the matching {folder} definition before the trim does anything."
    )
    return {"path": trim.path, "rule": "agent.unresolved_trim", "message": message, "severity": "error"}