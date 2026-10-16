"""Is the agent-written ``minecraft:recipe_smithing_trim`` something Bedrock can apply? (#86)

A Java ``minecraft:smithing_trim`` recipe names a *template* (the pattern), a
*base* (the armour being trimmed) and an *addition* (the material). Bedrock has
the same recipe shape and the structural oracle (``minecraft:recipe_smithing_trim``
in :mod:`portkit.validate.rules`) only checks that all three slots are
non-empty. So a model that wrote

    {"minecraft:recipe_smithing_trim": {"template": {...}, "base": {...},
    "addition": {"item": "examplemod:steel_ingot"}}}

for an agent_mod trim, with the deterministic path's note still in the task,
got the group to ``resolved``: the file parsed, every required slot was
non-empty, the validator was clean. The trim did nothing in game, though: a
Bedrock add-on can't register trim materials or trim patterns, so only
Mojang's own templates and materials ever apply.

So the residue agent holds its written trim recipes to a stricter, deterministic
rule, in the spirit of :mod:`portkit.agent.refs` and :mod:`portkit.agent.stats`:

- *Every* ``template`` and ``addition`` in a written ``minecraft:recipe_smithing_trim``
  must name a vanilla ``minecraft:`` item or tag. Any other id, item or tag, in
  the mod's namespace or another, is rejected, whatever the source ships: a
  Java ``data/<ns>/trim_material/`` or ``trim_pattern/`` definition does not
  help (Java keys those by material or pattern name, e.g. ``steel.json``, with
  the item in its ``ingredient`` / ``template_item`` field, and Bedrock can't
  use them at all). ``base`` is not gated here; the validator rule
  ``recipe.smithing_trim`` checks it (#272: BDS refuses a base that isn't
  wearable armor carrying ``minecraft:trimmable_armors``).

If a written trim violates the rule, :func:`finding` produces an
``agent.unresolved_trim`` validate error, and :func:`fabricated_trims` is the
list the residue agent rolls the group back for. The honest answer is to write
nothing and decline. Vanilla-only trims are taken on faith for the same reason
``refs.py`` takes vanilla ids on faith (the comment near :data:`VANILLA` in
that module spells it out).
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


def _is_trim_recipe(rel: str) -> bool:
    return rel.startswith("behavior_pack/recipes/") and rel.endswith(".json")


def fabricated_trims(out_tree: Path, written: list[str], source_root: Path) -> list[Trim]:
    """Trims the session wrote that name a template or addition with no working form.

    The result is a :class:`Trim` per offending slot; a single recipe can
    contribute up to two (one template, one addition). The rule is applied
    slot-by-slot: a vanilla slot passes, any other namespace fails.
    ``source_root`` is kept for symmetry with the sibling guards; nothing the
    source ships can make a non-vanilla trim slot work on Bedrock.
    """
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    recipes = [rel for rel in normalised if _is_trim_recipe(rel) and (out_tree / rel).is_file()]
    if not recipes:
        return []
    bad: list[Trim] = []
    for rel in recipes:
        for body in _trim_bodies(out_tree, rel):
            for slot in _TRIM_SLOTS:
                ident = _trim_ident(body.get(slot))
                if ident is None:
                    continue
                # An unnamespaced id means minecraft: on Bedrock, as in Java;
                # a Java-style leading "#" on a tag is ignored.
                namespace, sep, _ = ident.lstrip("#").partition(":")
                if not sep or namespace == _VANILLA:
                    continue  # vanilla ids are taken on faith
                bad.append(Trim(rel, slot, ident))
    return bad


def finding(trim: Trim) -> dict:
    """The validate-tool finding for one unresolved trim, as the agent sees it.

    Tells the agent the exact slot, the exact id, and why a written Bedrock
    recipe for it cannot apply anything: a Bedrock add-on can't apply a mod
    trim pattern or material, so the honest answer is to write nothing and
    decline with a one-sentence reason.
    """
    kind = "pattern (template)" if trim.where == "template" else "material (addition)"
    message = (
        f"{trim.where} names {trim.ident!r}, a non-vanilla trim {kind}. A Bedrock "
        "add-on can't apply a mod's trim patterns or trim materials, so a "
        "recipe_smithing_trim only does anything when its template and addition are "
        "vanilla minecraft: items or tags. Write nothing and decline: say that the "
        "trim has no Bedrock form because its "
        f"{'pattern' if trim.where == 'template' else 'material'} is not vanilla."
    )
    return {"path": trim.path, "rule": "agent.unresolved_trim", "message": message, "severity": "error"}
