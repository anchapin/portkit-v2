"""#442: leftover damage types are explained, not left unowned.

A Java damage type (``data/<ns>/damage_type/*.json``) no converter claimed is
``unowned`` residue. Bedrock has no data-driven damage types (its causes are
the fixed ``EntityDamageCause`` enum), so such a group is re-filed as the
explained ``no_bedrock_damage_type``. A file Java's own reader would reject
stays ``unowned``, and so does every other leftover.
Offline, ``examplemod`` only.
"""
import json
import shutil
from pathlib import Path

from portkit import damagetypes
from portkit.agent.residue import SKIP_KINDS
from portkit.model import Unhandled
from portkit.pipeline import convert

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "recipes_mod" / "input"


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body))


def _damage_type(name: str) -> dict:
    return {"message_id": f"death.attack.{name}", "scaling": "when_caused_by_living_non_player",
            "effects": ["hurt", "exhaustion"], "death_message_type": "default"}


def test_no_bedrock_damage_type_is_an_explained_kind():
    assert "no_bedrock_damage_type" in SKIP_KINDS
    assert damagetypes.KINDS <= set(SKIP_KINDS)


def test_refine_files_the_damage_types_of_a_jar(tmp_path):
    """Every damage type of the jar is a JSON object, so the whole group is
    re-filed and the file count is kept."""
    root = tmp_path
    _write(root, "data/examplemod/damage_type/lightning.json", _damage_type("lightning"))
    _write(root, "data/examplemod/damage_type/freeze.json", _damage_type("freeze"))
    unhandled = [Unhandled("data/examplemod/damage_type/", "unowned",
                            "2 file(s) no converter claims yet", count=2)]
    out = damagetypes.refine(unhandled, root, set())
    by = {(u.kind, u.source): u for u in out}
    assert ("unowned", "data/examplemod/damage_type/") not in by
    filed = by[("no_bedrock_damage_type", "data/examplemod/damage_type/")]
    assert filed.count == 2
    # The reason names the file count and the Bedrock side.
    assert "2 damage type(s)" in filed.reason
    assert "EntityDamageCause" in filed.reason
    assert "no damage-type registry" in filed.reason
    assert "lightning" in filed.reason and "freeze" in filed.reason
    assert sum(u.count for u in out) == sum(u.count for u in unhandled)


def test_a_file_java_would_reject_stays_unowned(tmp_path):
    """A damage type that is not a JSON object (one Java's reader rejects) and
    one that isn't JSON at all stay ``unowned`` (#442)."""
    root = tmp_path
    _write(root, "data/examplemod/damage_type/good.json", _damage_type("good"))
    _write(root, "data/examplemod/damage_type/list.json", [1, 2])
    _write(root, "data/examplemod/damage_type/broken.json", "{not json")
    unhandled = [Unhandled("data/examplemod/damage_type/", "unowned",
                            "3 file(s) no converter claims yet", count=3)]
    out = damagetypes.refine(unhandled, root, set())
    by = {(u.kind, u.source): u for u in out}
    assert by[("no_bedrock_damage_type", "data/examplemod/damage_type/")].count == 1
    left = by[("unowned", "data/examplemod/damage_type/")]
    assert left.count == 2
    assert sum(u.count for u in out) == sum(u.count for u in unhandled)


def test_a_damage_type_a_converter_claimed_is_untouched(tmp_path):
    """A damage type a converter already read is not re-filed: the group keeps
    only the files no converter claims."""
    root = tmp_path
    _write(root, "data/examplemod/damage_type/claimed.json", _damage_type("claimed"))
    _write(root, "data/examplemod/damage_type/left.json", _damage_type("left"))
    unhandled = [Unhandled("data/examplemod/damage_type/", "unowned",
                            "2 file(s) no converter claims yet", count=2)]
    out = damagetypes.refine(unhandled, root, {"data/examplemod/damage_type/claimed.json"})
    by = {(u.kind, u.source): u for u in out}
    filed = by[("no_bedrock_damage_type", "data/examplemod/damage_type/")]
    assert filed.count == 1
    assert "left" in filed.reason and "claimed" not in filed.reason
    assert ("unowned", "data/examplemod/damage_type/") not in by
    assert sum(u.count for u in out) == 1


def test_other_leftovers_are_unchanged(tmp_path):
    """A group of another kind and an ``unowned`` group of another folder are
    returned as they were."""
    root = tmp_path
    _write(root, "data/examplemod/damage_type/lightning.json", _damage_type("lightning"))
    _write(root, "data/examplemod/predicate/other.json", {"type": "examplemod:other"})
    unhandled = [
        Unhandled("data/examplemod/damage_type/", "unowned", "1 file(s) no converter claims yet", count=1),
        Unhandled("data/examplemod/predicate/", "unowned", "1 file(s) no converter claims yet", count=1),
        Unhandled("data/examplemod/recipe/grind.json", "recipe", "unknown recipe type", count=1),
    ]
    out = damagetypes.refine(unhandled, root, set())
    by = {(u.kind, u.source): u for u in out}
    assert by[("no_bedrock_damage_type", "data/examplemod/damage_type/")].count == 1
    assert by[("unowned", "data/examplemod/predicate/")].count == 1
    assert by[("recipe", "data/examplemod/recipe/grind.json")].count == 1


def test_pipeline_files_every_damage_type(tmp_path):
    src = tmp_path / "mod"
    shutil.copytree(FIXTURE, src)
    _write(src, "data/examplemod/damage_type/lightning.json", _damage_type("lightning"))
    _write(src, "data/examplemod/damage_type/freeze.json", _damage_type("freeze"))
    _write(src, "data/examplemod/damage_type/odd.json", [1, 2])
    result = convert(src, tmp_path / "out")
    got = sorted((u.kind, u.source, u.count) for u in result.unhandled
                  if "/damage_type/" in u.source)
    assert got == [
        ("no_bedrock_damage_type", "data/examplemod/damage_type/", 2),
        ("unowned", "data/examplemod/damage_type/", 1),
    ]
    # Nothing was converted: the pack holds no damage type.
    assert not list((tmp_path / "out" / "behavior_pack").rglob("*damage_type*"))
