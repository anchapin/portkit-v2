"""Property tests for the Java-to-Bedrock converters (#434).

The example tests in ``test_blocks.py`` and ``test_accounting.py`` pin one
fixture each. These do the same job over generated input: many small mods,
each built in memory (JSON bodies written into a temp directory, no jars, no
network, no mod downloads), converted by the same converter entry points the
example tests call.

Two properties are asserted, and both are about the converters' promises:

* **Round-trip stability.** Where a round trip is defined -- a Java id
  becoming a Bedrock identifier and being read back -- the Bedrock definition
  says the same id the Java source had, and the same input converts to the
  same output every time.
* **No silent loss.** Every input element (a block, an item) either appears
  in the output or is accounted for in the conversion result: a residue entry
  naming it, or a note saying what was dropped. Nothing vanishes between the
  input tree and the result.

The properties are additive: they say nothing the example tests do not, they
just say it for input nobody wrote down by hand.

A Java block whose id holds a slash (its blockstate file sits in a subfolder)
is converted like any other block (#436): the block converter walks the
blockstate folders, so such a block is neither dropped nor left unaccounted.
"""
from __future__ import annotations

import json
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from portkit.converters import blocks, items
from portkit.model import SourceMod
from portkit.pipeline import convert as pipeline_convert

NAMESPACE = "examplemod"

# The repo's conftest fixtures are function-scoped, so hypothesis would warn
# that they are shared between examples. They only pin the offline environment
# (no network, no reference cache) and are re-read per test, so the warning
# says nothing about these properties.
SETTINGS = settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# --- input builders -------------------------------------------------------


def _write_json(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")


def _block_mod(root: Path, names: list[str]) -> SourceMod:
    """A mod whose blocks are plain cubes, one texture each."""
    assets = root / "assets" / NAMESPACE
    for name in names:
        _write_json(
            assets / "blockstates" / f"{name}.json",
            {"variants": {"": {"model": f"{NAMESPACE}:block/{name}"}}},
        )
        _write_json(
            assets / "models" / "block" / f"{name}.json",
            {"parent": "minecraft:block/cube_all",
             "textures": {"all": f"{NAMESPACE}:block/{name}"}},
        )
        _write_png(assets / "textures" / "block" / f"{name}.png")
    return SourceMod(root=root, namespace=NAMESPACE)


def _item_mod(root: Path, names: list[str], registered: bool = True,
              parent: str = "minecraft:item/generated") -> SourceMod:
    """A mod whose items are flat icons, one texture each.

    ``registered`` says whether a lang key names each item: Java registers an
    item, and the converter writes a Bedrock item only for a registered one.
    ``parent`` is the vanilla model parent, so a held item (a tool) can be
    asked for as well.
    """
    assets = root / "assets" / NAMESPACE
    lang: dict[str, str] = {}
    for name in names:
        _write_json(
            assets / "models" / "item" / f"{name}.json",
            {"parent": parent, "textures": {"layer0": f"{NAMESPACE}:item/{name}"}},
        )
        _write_png(assets / "textures" / "item" / f"{name}.png")
        if registered:
            lang[f"item.{NAMESPACE}.{name}"] = name
    _write_json(assets / "lang" / "en_us.json", lang)
    return SourceMod(root=root, namespace=NAMESPACE)


def _pipeline_mod(root: Path, blocks_: list[str], items_: list[str]) -> None:
    """A mod directory with blocks and items, as the pipeline reads one."""
    assets = root / "assets" / NAMESPACE
    for name in blocks_:
        _write_json(
            assets / "blockstates" / f"{name}.json",
            {"variants": {"": {"model": f"{NAMESPACE}:block/{name}"}}},
        )
        _write_json(
            assets / "models" / "block" / f"{name}.json",
            {"parent": "minecraft:block/cube_all",
             "textures": {"all": f"{NAMESPACE}:block/{name}"}},
        )
        _write_png(assets / "textures" / "block" / f"{name}.png")
    lang: dict[str, str] = {}
    for name in items_:
        _write_json(
            assets / "models" / "item" / f"{name}.json",
            {"parent": "minecraft:item/generated",
             "textures": {"layer0": f"{NAMESPACE}:item/{name}"}},
        )
        _write_png(assets / "textures" / "item" / f"{name}.png")
        lang[f"item.{NAMESPACE}.{name}"] = name
    _write_json(assets / "lang" / "en_us.json", lang)


# --- strategies -----------------------------------------------------------

# A Java id's name part: lowercase letters, digits and underscores.
_name = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
                min_size=1, max_size=8)


@st.composite
def _names(draw, min_size: int = 1, max_size: int = 4) -> list[str]:
    return draw(st.lists(_name, min_size=min_size, max_size=max_size, unique=True))


# --- helpers --------------------------------------------------------------


def _java_id(identifier: str) -> tuple[str, str]:
    """The Java id a Bedrock identifier stands for."""
    namespace, _, name = identifier.partition(":")
    return namespace, name


def _accounted(result, needle: str) -> bool:
    """Whether the result says something about ``needle``."""
    return any(
        needle in entry.source or needle in entry.reason
        for entry in result.unhandled
    ) or any(needle in note for note in result.notes)


# --- blocks ---------------------------------------------------------------


@SETTINGS
@given(names=_names())
def test_block_definitions_round_trip_to_their_java_ids(names, tmp_path_factory):
    """A Java block id survives the conversion: the Bedrock definition says
    the same id, and reading it back gives the Java id again."""
    root = tmp_path_factory.mktemp("block_mod")
    mod = _block_mod(root, names)
    result = blocks.convert(mod)

    for name in names:
        path = f"blocks/{name}.json"
        assert path in result.files, f"{name} produced no Bedrock definition"
        body = result.files[path]["minecraft:block"]
        identifier = body["description"]["identifier"]
        assert identifier == f"{NAMESPACE}:{name}"
        # The round trip: Bedrock id -> Java id -> the same Bedrock id.
        assert _java_id(identifier) == (NAMESPACE, name)
        assert body["components"]["minecraft:material_instances"] == {
            "*": {"texture": f"{NAMESPACE}:{name}"}
        }


@SETTINGS
@given(names=_names())
def test_block_conversion_is_stable(names, tmp_path_factory):
    """The same input converts to the same output every time."""
    root = tmp_path_factory.mktemp("block_mod")
    mod = _block_mod(root, names)
    first = blocks.convert(mod)
    second = blocks.convert(mod)
    assert first.files == second.files
    assert first.unhandled == second.unhandled
    assert first.notes == second.notes


@SETTINGS
@given(names=_names())
def test_no_block_is_lost(names, tmp_path_factory):
    """Every block of the input is either converted or accounted for."""
    root = tmp_path_factory.mktemp("block_mod")
    mod = _block_mod(root, names)
    result = blocks.convert(mod)

    for name in names:
        rel = f"assets/{NAMESPACE}/blockstates/{name}.json"
        # The converter looked at it: nothing was left unseen.
        assert rel in result.consumed
        assert f"blocks/{name}.json" in result.files or _accounted(result, name), (
            f"{name} was neither converted nor reported"
        )
    # Nothing else was written: one definition per block, no phantom blocks.
    assert set(result.files) == {f"blocks/{name}.json" for name in names}


@SETTINGS
@given(names=_names())
def test_a_refused_block_is_reported_with_its_reason(names, tmp_path_factory):
    """A block the converter cannot carry is residue naming the block, not a
    quiet omission."""
    root = tmp_path_factory.mktemp("block_mod")
    assets = root / "assets" / NAMESPACE
    # Two variants: Java picks one per state, Bedrock needs explicit states.
    for name in names:
        _write_json(
            assets / "blockstates" / f"{name}.json",
            {"variants": {"a": {"model": f"{NAMESPACE}:block/{name}"},
                          "b": {"model": f"{NAMESPACE}:block/{name}"}}},
        )
        _write_json(
            assets / "models" / "block" / f"{name}.json",
            {"parent": "minecraft:block/cube_all",
             "textures": {"all": f"{NAMESPACE}:block/{name}"}},
        )
    mod = SourceMod(root=root, namespace=NAMESPACE)
    result = blocks.convert(mod)

    assert result.files == {}
    for name in names:
        rel = f"assets/{NAMESPACE}/blockstates/{name}.json"
        entries = [entry for entry in result.unhandled if entry.source == rel]
        assert entries, f"{name} was dropped without a residue entry"
        assert entries[0].count == 1
        # The entry names the block (its source) and says why it stayed.
        assert entries[0].source.endswith(f"{name}.json")
        assert entries[0].reason


# --- items ----------------------------------------------------------------


@SETTINGS
@given(names=_names())
def test_item_definitions_round_trip_to_their_java_ids(names, tmp_path_factory):
    """A Java item id survives the conversion: the Bedrock definition says
    the same id, and reading it back gives the Java id again."""
    root = tmp_path_factory.mktemp("item_mod")
    mod = _item_mod(root, names)
    result = items.convert(mod)

    for name in names:
        path = f"items/{name}.json"
        assert path in result.files, f"{name} produced no Bedrock definition"
        body = result.files[path]["minecraft:item"]
        identifier = body["description"]["identifier"]
        assert identifier == f"{NAMESPACE}:{name}"
        # The round trip: Bedrock id -> Java id -> the same Bedrock id.
        assert _java_id(identifier) == (NAMESPACE, name)
        assert body["components"]["minecraft:icon"] == f"{NAMESPACE}:{name}"


@SETTINGS
@given(names=_names())
def test_a_held_item_keeps_its_held_pose(names, tmp_path_factory):
    """A tool (a handheld model) converts as the same item, held like one."""
    root = tmp_path_factory.mktemp("item_mod")
    mod = _item_mod(root, names, parent="minecraft:item/handheld")
    result = items.convert(mod)

    for name in names:
        body = result.files[f"items/{name}.json"]["minecraft:item"]
        assert body["components"]["minecraft:hand_equipped"] is True
        assert body["components"]["minecraft:icon"] == f"{NAMESPACE}:{name}"


@SETTINGS
@given(names=_names())
def test_no_item_is_lost(names, tmp_path_factory):
    """Every item of the input is either converted or accounted for."""
    root = tmp_path_factory.mktemp("item_mod")
    mod = _item_mod(root, names)
    result = items.convert(mod)

    for name in names:
        rel = f"assets/{NAMESPACE}/models/item/{name}.json"
        assert rel in result.consumed
        assert f"items/{name}.json" in result.files or _accounted(result, name), (
            f"{name} was neither converted nor reported"
        )
    assert set(result.files) == {f"items/{name}.json" for name in names}


@SETTINGS
@given(names=_names())
def test_an_unregistered_item_is_logged_not_dropped(names, tmp_path_factory):
    """An item model Java does not register is no Bedrock item, but the
    result says so: the model's texture is not dropped in silence."""
    root = tmp_path_factory.mktemp("item_mod")
    mod = _item_mod(root, names, registered=False)
    result = items.convert(mod)

    assert result.files == {}
    for name in names:
        rel = f"assets/{NAMESPACE}/models/item/{name}.json"
        assert rel in result.consumed
        assert _accounted(result, name), f"{name} was dropped without saying so"


@SETTINGS
@given(names=_names())
def test_a_blocks_own_item_is_left_to_bedrock(names, tmp_path_factory):
    """The item model of a block is the block's item: Bedrock registers one
    for every custom block, so the converter must not write a second
    definition for it."""
    root = tmp_path_factory.mktemp("mod")
    assets = root / "assets" / NAMESPACE
    for name in names:
        _write_json(
            assets / "blockstates" / f"{name}.json",
            {"variants": {"": {"model": f"{NAMESPACE}:block/{name}"}}},
        )
        _write_json(
            assets / "models" / "block" / f"{name}.json",
            {"parent": "minecraft:block/cube_all",
             "textures": {"all": f"{NAMESPACE}:block/{name}"}},
        )
        _write_json(
            assets / "models" / "item" / f"{name}.json",
            {"parent": "minecraft:item/generated",
             "textures": {"layer0": f"{NAMESPACE}:item/{name}"}},
        )
        _write_png(assets / "textures" / "block" / f"{name}.png")
        _write_png(assets / "textures" / "item" / f"{name}.png")
    _write_json(assets / "lang" / "en_us.json",
                {f"item.{NAMESPACE}.{name}": name for name in names})
    mod = SourceMod(root=root, namespace=NAMESPACE)

    block_result = blocks.convert(mod)
    assert set(block_result.files) == {f"blocks/{name}.json" for name in names}
    emitted = {f"{NAMESPACE}:{name}" for name in names}
    item_result = items.convert(mod, emitted_blocks=emitted)

    for name in names:
        rel = f"assets/{NAMESPACE}/models/item/{name}.json"
        assert rel in item_result.consumed
        assert f"items/{name}.json" not in item_result.files


# --- the pipeline ---------------------------------------------------------


@SETTINGS
@given(names=_names())
def test_every_staged_file_is_accounted_for(names, tmp_path_factory):
    """The whole run leaves nothing unowned: every file of the mod is either
    in the pack or in the residue, and the books balance."""
    root = tmp_path_factory.mktemp("mod")
    block_names = [f"b_{name}" for name in names]
    item_names = [f"i_{name}" for name in names]
    _pipeline_mod(root, block_names, item_names)
    result = pipeline_convert(root, root.parent / "out")

    assert [u for u in result.unhandled if u.kind == "unowned"] == []
    assert result.residue_count == 0
    assert result.coverage == 100.0


@SETTINGS
@given(names=_names())
def test_ids_round_trip_through_the_pack(names, tmp_path_factory):
    """A Java id read back out of the pack is the Java id that went in."""
    root = tmp_path_factory.mktemp("mod")
    block_names = [f"b_{name}" for name in names]
    item_names = [f"i_{name}" for name in names]
    _pipeline_mod(root, block_names, item_names)
    result = pipeline_convert(root, root.parent / "out")

    for name in block_names:
        body = json.loads(
            (result.tree / "behavior_pack" / "blocks" / f"{name}.json").read_text()
        )
        identifier = body["minecraft:block"]["description"]["identifier"]
        assert identifier == f"{NAMESPACE}:{name}"
        assert _java_id(identifier) == (NAMESPACE, name)
    for name in item_names:
        body = json.loads(
            (result.tree / "behavior_pack" / "items" / f"{name}.json").read_text()
        )
        identifier = body["minecraft:item"]["description"]["identifier"]
        assert identifier == f"{NAMESPACE}:{name}"
        assert _java_id(identifier) == (NAMESPACE, name)


# --- a block whose id holds a slash ----------------------------------------


def test_a_block_in_a_subfolder_is_not_lost(tmp_path):
    """A block whose id holds a slash is converted or reported, like any
    other block (#436)."""
    assets = tmp_path / "assets" / NAMESPACE
    _write_json(
        assets / "blockstates" / "machine" / "ore.json",
        {"variants": {"": {"model": f"{NAMESPACE}:block/ore"}}},
    )
    _write_json(
        assets / "models" / "block" / "ore.json",
        {"parent": "minecraft:block/cube_all",
         "textures": {"all": f"{NAMESPACE}:block/ore"}},
    )
    _write_png(assets / "textures" / "block" / "ore.png")
    mod = SourceMod(root=tmp_path, namespace=NAMESPACE)

    result = blocks.convert(mod)

    for path in (assets / "blockstates").rglob("*.json"):
        rel = str(path.relative_to(tmp_path))
        assert rel in result.consumed or _accounted(result, path.stem), (
            f"{rel} was neither converted nor reported"
        )


def test_a_block_in_a_subfolder_converts_with_its_own_id(tmp_path):
    """The block of a subfolder converts under the id Java gives it: the
    blockstate's folder is part of the id (#436)."""
    assets = tmp_path / "assets" / NAMESPACE
    _write_json(
        assets / "blockstates" / "machine" / "ore.json",
        {"variants": {"": {"model": f"{NAMESPACE}:block/ore"}}},
    )
    _write_json(
        assets / "models" / "block" / "ore.json",
        {"parent": "minecraft:block/cube_all",
         "textures": {"all": f"{NAMESPACE}:block/ore"}},
    )
    _write_png(assets / "textures" / "block" / "ore.png")
    mod = SourceMod(root=tmp_path, namespace=NAMESPACE)

    result = blocks.convert(mod)

    assert result.unhandled == []
    assert "assets/examplemod/blockstates/machine/ore.json" in result.consumed
    body = result.files["blocks/machine/ore.json"]["minecraft:block"]
    assert body["description"]["identifier"] == f"{NAMESPACE}:machine/ore"

