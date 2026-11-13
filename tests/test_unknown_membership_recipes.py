"""Recipe sub-reason 5 (#302): a recipe refused only because a tag
ingredient's membership isn't knowable from the jar.

Three shapes, one per clause of the issue's breakdown:
  (i)   the tag has no members knowable from the jar at all (a vanilla tag
        named by the recipe, no tag data anywhere to read);
  (ii)  the tag's members are themselves a tag whose membership isn't
        knowable (nested tag, unresolvable here);
  (iii) partial share: the jar ships its own share of a vanilla tag, but
        vanilla's share isn't there to read, so the whole isn't knowable.

In every shape the recipe stays residue under the explained kind
``recipe_unknown_membership`` — never converted with an invented or
narrowed membership, and never left in the plain ``recipe`` bucket that
hides the cause. Added by the supervisor at collection: the worker's
change shipped the classification without its tests.
"""
import json
from pathlib import Path

from portkit.converters import recipes
from portkit.model import SourceMod


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _mod(root: Path, recipe, *, loader="neoforge", minecraft="1.21.1", tag_files=None,
         name="thing"):
    lane = "recipe" if loader in ("neoforge", "fabric") else "recipes"
    _write(root, f"data/examplemod/{lane}/{name}.json", recipe)
    for rel, values in (tag_files or {}).items():
        _write(root, rel, {"values": values})
    return SourceMod(root=root, namespace="examplemod", loader=loader,
                     minecraft=minecraft, mods=None, requires=None)


def _kinds(result):
    return [(u.kind, u.reason) for u in result.unhandled]


def test_no_members_knowable_from_the_jar(tmp_path):
    """(i) A vanilla tag, no tag data: membership is simply not there to read."""
    recipe = {"type": "minecraft:smelting", "ingredient": "#minecraft:eggs",
              "result": "examplemod:fried_egg"}
    result = recipes.convert(_mod(tmp_path, recipe), emitted={})
    assert not [k for k in result.files if k.startswith("recipes/")]
    (kind, reason), = _kinds(result)
    assert kind == recipes.UNKNOWN_MEMBERSHIP
    assert "minecraft:eggs" in reason
    assert "isn't knowable" in reason


def test_nested_tag_membership_not_knowable(tmp_path):
    """(ii) The jar's tag nests a shared tag no data here can resolve."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [{"tag": "examplemod:alloys"}],
              "result": {"id": "examplemod:blend"}}
    mod = _mod(tmp_path, recipe, tag_files={
        "data/examplemod/tags/items/alloys.json": ["#c:ingots/steel"],
    })
    result = recipes.convert(mod, emitted={})
    assert not [k for k in result.files if k.startswith("recipes/")]
    (kind, reason), = _kinds(result)
    assert kind == recipes.UNKNOWN_MEMBERSHIP
    assert "examplemod:alloys" in reason


def test_partial_share_of_a_vanilla_tag(tmp_path):
    """(iii) The jar's file for a vanilla tag is only its own share of it."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [{"tag": "minecraft:leaves"}],
              "result": {"id": "examplemod:mulch"}}
    mod = _mod(tmp_path, recipe, loader=None, minecraft=None, tag_files={
        "data/minecraft/tags/items/leaves.json": ["examplemod:steel_leaves"],
    })
    result = recipes.convert(mod, emitted={})
    assert not [k for k in result.files if k.startswith("recipes/")]
    (kind, reason), = _kinds(result)
    assert kind == recipes.UNKNOWN_MEMBERSHIP
    assert "minecraft:leaves" in reason
    assert "only its own share" in reason
