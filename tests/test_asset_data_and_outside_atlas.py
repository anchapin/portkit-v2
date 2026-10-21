"""#346 (pending Alex, picks 1a and 2a): the last two kinds of Comforts' residue, generically.

1a. ``other_mod_data`` for ``assets/<ns>/<dir>/``: a folder Minecraft's client
    doesn't read, every file a JSON object, and no class of the jar names the
    folder in a string. Data only another mod's reloader reads.
2a. ``vanilla_texture_outside_atlas``: a block refused because its model borrows
    a vanilla texture from outside Java's block/ and item/ folders, which
    Bedrock's block and item atlases don't list. Still not converted.

Offline, ``examplemod`` only; no mod names (#220).
"""
import json
from pathlib import Path

from portkit import worldgen
from portkit.agent.residue import SKIP_KINDS
from portkit.converters import blocks, models
from portkit.model import Unhandled
from portkit.pipeline import unowned


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(json.dumps(body))


class _CF:
    def __init__(self, strings):
        self.pool = [None] + [("utf8", s) for s in strings]
        self._strings = [None] + list(strings)
        self.super_name = "java/lang/Object"

    def constant(self, i):
        return self._strings[i]


class _Classes:
    def __init__(self, classes):
        self._c = classes

    def names(self):
        return sorted(self._c)

    def get(self, name, remap=True):
        return self._c.get(name)


_RULE = {"blocks": ["#examplemod:beds"], "directions": ["north"],
         "connecting_blocks": ["#examplemod:beds"]}


def _refine(root, classes):
    return worldgen.refine(unowned(root, set()), root, set(), {"examplemod"}, classes)


def test_both_kinds_are_explained():
    assert {"other_mod_data", "vanilla_texture_outside_atlas"} <= set(SKIP_KINDS)


def test_an_unread_asset_folder_of_json_is_other_mod_data(tmp_path):
    _write(tmp_path, "assets/examplemod/connect_rules/bed_head.json", _RULE)
    _write(tmp_path, "assets/examplemod/connect_rules/bed_foot.json", _RULE)
    out = _refine(tmp_path, _Classes({"com/example/Mod": _CF(["examplemod", "bed"])}))
    entry = next(u for u in out if u.source == "assets/examplemod/connect_rules/")
    assert entry.kind == "other_mod_data"
    assert entry.count == 2
    assert "`connect_rules/` is not a folder of assets Minecraft's client reads" in entry.reason
    assert "no class of the jar names `connect_rules`" in entry.reason
    assert not [u for u in out if u.kind == "unowned"]


def test_a_folder_the_jar_names_stays_unowned(tmp_path):
    # The mod's own code may read it (a reloader of its own): not explained.
    _write(tmp_path, "assets/examplemod/connect_rules/bed_head.json", _RULE)
    out = _refine(tmp_path, _Classes({"com/example/Rules": _CF(["examplemod:connect_rules/"])}))
    assert {(u.source, u.kind) for u in out} == {("assets/examplemod/connect_rules/", "unowned")}


def test_non_json_or_client_folders_or_no_classes_stay_unowned(tmp_path):
    _write(tmp_path, "assets/examplemod/connect_rules/bed_head.json", _RULE)
    _write(tmp_path, "assets/examplemod/connect_rules/notes.txt", b"not data")
    _write(tmp_path, "assets/examplemod/mixed/list.json", ["a list, not an object"])
    _write(tmp_path, "assets/examplemod/texts/end.json", {"a": 1})
    classes = _Classes({"com/example/Mod": _CF(["examplemod"])})
    kinds = {(u.source, u.kind) for u in _refine(tmp_path, classes)}
    assert ("assets/examplemod/connect_rules/", "unowned") in kinds
    assert ("assets/examplemod/mixed/", "unowned") in kinds
    assert not any(kind == "other_mod_data" for _, kind in kinds)

    only_json = tmp_path / "second"
    _write(only_json, "assets/examplemod/connect_rules/bed_head.json", _RULE)
    # Without the jar's classes its own code can't be ruled out.
    assert {u.kind for u in _refine(only_json, None)} == {"unowned"}


def test_a_block_on_an_entity_texture_is_explained_and_keeps_its_reason():
    why = f"model points at 'minecraft:entity/knot', {models.OUTSIDE_ATLAS}"
    residue = [
        Unhandled("assets/examplemod/blockstates/knot.json", "block", why),
        Unhandled("assets/examplemod/blockstates/post.json", "block", f"facing model: {why}"),
        Unhandled("assets/examplemod/blockstates/other.json", "block", "model has no elements"),
        Unhandled("assets/examplemod/models/item/knot.json", "item", why),
    ]
    out = blocks.refine_outside_atlas(residue)
    kinds = {u.source: u.kind for u in out}
    assert kinds == {
        "assets/examplemod/blockstates/knot.json": "vanilla_texture_outside_atlas",
        "assets/examplemod/blockstates/post.json": "vanilla_texture_outside_atlas",
        "assets/examplemod/blockstates/other.json": "block",
        # Items keep today's kind (pick 3a).
        "assets/examplemod/models/item/knot.json": "item",
    }
    knot = out[0]
    assert knot.reason.startswith(why)
    assert "list no copy of `minecraft:entity/knot`" in knot.reason


def test_vanilla_texture_names_the_outside_atlas_reason():
    key, file, why = models.vanilla_texture("minecraft:entity/knot", "examplemod")
    assert key is None and file is None
    assert why == f"model points at 'minecraft:entity/knot', {models.OUTSIDE_ATLAS}"


def test_a_block_and_item_texture_reason_is_not_re_filed():
    # A vanilla block/ texture missing from the index is a different gap.
    why = "model points at 'minecraft:block/knot', a vanilla texture Bedrock has no file of that name for"
    out = blocks.refine_outside_atlas([Unhandled("assets/examplemod/blockstates/k.json", "block", why)])
    assert out[0].kind == "block"


def test_a_converted_mod_files_the_block_through_the_pipeline(tmp_path):
    from portkit.pipeline import convert

    src = tmp_path / "src"
    _write(src, "assets/examplemod/blockstates/knot.json", {"variants": {"": {"model": "examplemod:block/knot"}}})
    _write(src, "assets/examplemod/models/block/knot.json", {
        "textures": {"particle": "minecraft:entity/knot", "t": "minecraft:entity/knot"},
        "elements": [{"from": [6, 0, 6], "to": [10, 4, 10],
                      "faces": {f: {"uv": [0, 0, 4, 4], "texture": "#t"}
                                for f in ("north", "south", "east", "west", "up", "down")}}],
    })
    # A block that converts, so the mod ships and the shipping passes run.
    _write(src, "assets/examplemod/blockstates/stone.json", {"variants": {"": {"model": "examplemod:block/stone"}}})
    _write(src, "assets/examplemod/models/block/stone.json",
           {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/stone"}})
    _write(src, "assets/examplemod/textures/block/stone.png", _png16())
    out = tmp_path / "out"
    convert(src, out, namespace="examplemod", emit_addon=False)
    residue = json.loads((out / "unhandled.json").read_text())
    knot = [u for u in residue if u["source"] == "assets/examplemod/blockstates/knot.json"]
    assert [u["kind"] for u in knot] == ["vanilla_texture_outside_atlas"]


def _png16() -> bytes:
    import struct
    import zlib

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
