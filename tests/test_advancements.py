"""#340 (part of #277): leftover advancements are owned by residue or explained.

A recipe advancement whose recipes are all residue goes with them
(``owned_by_residue``). A story advancement, a recipe advancement whose recipes
ship as furnace recipes (no Bedrock ``unlock`` field) and one naming recipes the
jar doesn't define are ``no_bedrock_advancement``. Anything else stays
``unowned``. A crafting recipe's advancement is still claimed by #260.
Offline, ``examplemod`` only.
"""
import json
import shutil
from pathlib import Path

from portkit import advancements
from portkit.agent.residue import SKIP_KINDS
from portkit.model import Unhandled
from portkit.pipeline import convert

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "recipes_mod" / "input"


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body))


def _recipe_adv(recipe: str, item: str = "minecraft:iron_ingot", **rewards) -> dict:
    return {
        "parent": "minecraft:recipes/root",
        "criteria": {
            "has_item": {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": item}]}},
            "has_the_recipe": {"trigger": "minecraft:recipe_unlocked", "conditions": {"recipe": recipe}},
        },
        "requirements": [["has_item", "has_the_recipe"]],
        "rewards": {"recipes": [recipe], **rewards},
    }


def _story(**rewards) -> dict:
    adv = {"display": {"icon": {"id": "minecraft:stone"}, "title": "t", "description": "d"},
           "criteria": {"tamed": {"trigger": "minecraft:tame_animal"}}}
    if rewards:
        adv["rewards"] = rewards
    return adv


def test_no_bedrock_advancement_is_an_explained_kind():
    assert "no_bedrock_advancement" in SKIP_KINDS
    assert advancements.KINDS <= set(SKIP_KINDS)
    assert "owned_by_residue" in SKIP_KINDS


def test_classify_cases(tmp_path):
    root = tmp_path
    _write(root, "data/examplemod/recipe/refused.json", {"type": "examplemod:grinding"})
    _write(root, "data/examplemod/recipe/smelted.json", {"type": "minecraft:smelting"})
    _write(root, "data/examplemod/recipe/other.json", {"type": "minecraft:crafting_shaped"})
    files = {
        "data/examplemod/advancement/recipes/refused.json": _recipe_adv("examplemod:refused"),
        "data/examplemod/advancement/recipes/smelted.json": _recipe_adv("examplemod:smelted"),
        "data/examplemod/advancement/recipes/absent.json": _recipe_adv("minecraft:refused"),
        "data/examplemod/advancement/recipes/mixed.json": {
            **_recipe_adv("examplemod:refused"), "rewards": {"recipes": ["examplemod:refused", "examplemod:nope"]}},
        "data/examplemod/advancement/recipes/with_xp.json": _recipe_adv("examplemod:refused", experience=5),
        "data/examplemod/advancement/recipes/unshipped.json": _recipe_adv("examplemod:other"),
        "data/examplemod/advancement/story/tame.json": _story(),
        "data/examplemod/advancement/story/rich.json": _story(experience=100, loot=["examplemod:chests/x"]),
        "data/examplemod/advancement/story/bad_criteria.json": {"criteria": [], "display": {}},
        "data/examplemod/advancement/story/bad_reward.json": {**_story(), "rewards": {"bonus": 1}},
        "data/examplemod/advancement/story/not_object.json": [1, 2],
    }
    for rel, body in files.items():
        _write(root, rel, body)
    _write(root, "data/examplemod/advancement/story/broken.json", "{not json")
    residue = {"data/examplemod/recipe/refused.json": "recipe"}
    bodies = {"data/examplemod/recipe/smelted.json": {"minecraft:recipe_furnace"},
              "data/examplemod/recipe/other.json": {"minecraft:recipe_shaped"}}
    got = advancements.classify(root, sorted(files) + ["data/examplemod/advancement/story/broken.json"],
                                residue, bodies)
    kinds = {rel.rsplit("/", 1)[-1]: (k, c) for rel, (k, c, _) in got.items()}
    assert kinds == {
        "refused.json": ("owned_by_residue", "recipe"),
        "smelted.json": ("no_bedrock_advancement", "furnace"),
        "absent.json": ("no_bedrock_advancement", "absent"),
        "tame.json": ("no_bedrock_advancement", "story"),
        "rich.json": ("no_bedrock_advancement", "story"),
    }


def test_refine_counts_and_reasons(tmp_path):
    root = tmp_path
    _write(root, "data/examplemod/recipe/refused.json", {"type": "examplemod:grinding"})
    _write(root, "data/examplemod/advancement/recipes/refused.json", _recipe_adv("examplemod:refused"))
    _write(root, "data/examplemod/advancement/story/rich.json", _story(experience=100))
    _write(root, "data/examplemod/advancement/story/broken.json", "{not json")
    unhandled = [
        Unhandled("data/examplemod/recipe/refused.json", "recipe", "unknown recipe type"),
        Unhandled("data/examplemod/advancement/", "unowned", "3 file(s) no converter claims yet", count=3),
    ]
    out = advancements.refine(unhandled, root, set(), {})
    by = {(u.kind, u.source): u for u in out}
    assert by[("unowned", "data/examplemod/advancement/")].count == 1
    owned = by[("owned_by_residue", "data/examplemod/advancement/recipes/")]
    assert owned.count == 1 and "data/examplemod/recipe/refused.json" in owned.reason
    story = by[("no_bedrock_advancement", "data/examplemod/advancement/story/")]
    assert story.count == 1
    assert "experience 100" in story.reason and "never gives more than Java" in story.reason
    assert "fixed list" in story.reason
    # Nothing else moved, and the file total is kept.
    assert sum(u.count for u in out) == sum(u.count for u in unhandled)


def test_pipeline_files_every_advancement(tmp_path):
    src = tmp_path / "mod"
    shutil.copytree(FIXTURE, src)
    adv = "data/examplemod/advancements/recipes"
    _write(src, "data/examplemod/recipes/grind.json", {"type": "examplemod:grinding", "input": "x"})
    _write(src, f"{adv}/iron_frame.json", _recipe_adv("examplemod:iron_frame"))
    _write(src, f"{adv}/blasted_ingot.json", _recipe_adv("examplemod:blasted_ingot"))
    _write(src, f"{adv}/grind.json", _recipe_adv("examplemod:grind"))
    _write(src, f"{adv}/missing.json", _recipe_adv("minecraft:missing"))
    _write(src, "data/examplemod/advancements/story/tame.json", _story(experience=10))
    _write(src, "data/examplemod/advancements/story/odd.json", {"criteria": "x"})
    result = convert(src, tmp_path / "out")
    adv_entries = [u for u in result.unhandled if "/advancements/" in u.source]
    got = sorted((u.kind, u.source, u.count) for u in adv_entries)
    assert got == [
        ("no_bedrock_advancement", "data/examplemod/advancements/recipes/", 1),  # blasted_ingot: furnace
        ("no_bedrock_advancement", "data/examplemod/advancements/recipes/", 1),  # missing: absent
        ("no_bedrock_advancement", "data/examplemod/advancements/story/", 1),
        ("owned_by_residue", "data/examplemod/advancements/recipes/", 1),  # grind
        ("unowned", "data/examplemod/advancements/", 1),  # odd.json
    ]
    # The crafting recipe's advancement is still claimed for its Bedrock unlock (#260): it is in no
    # entry above, and the recipe carries unlock data.
    frame = json.loads((tmp_path / "out" / "behavior_pack" / "recipes" / "iron_frame.json").read_text())
    assert "unlock" in frame["minecraft:recipe_shaped"]
