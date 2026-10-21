"""#277 unowned: leftover models and textures, explained from the jar's own references."""
import json

from portkit import ownership
from portkit.model import Unhandled


def _jar(tmp_path, files):
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(json.dumps(body))
    return tmp_path


PNG = b"\x89PNG\r\n\x1a\n"


def test_models_and_textures_of_a_refused_block_are_owned_by_its_residue(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/blockstates/door.json": {"variants": {"open=true": {"model": "m:block/door_open"},
                                                        "open=false": {"model": "m:block/door"}}},
        "assets/m/models/block/door_open.json": {"parent": "m:block/door_base", "textures": {"all": "m:block/door"}},
        "assets/m/models/block/door.json": {"parent": "m:block/door_base"},
        "assets/m/models/block/door_base.json": {"elements": []},
        "assets/m/textures/block/door.png": PNG,
    })
    found = ownership.classify(root, [
        "assets/m/models/block/door_open.json", "assets/m/models/block/door.json",
        "assets/m/models/block/door_base.json", "assets/m/textures/block/door.png",
    ], consumed={"assets/m/blockstates/door.json"}, residue_sources={"assets/m/blockstates/door.json"})
    assert {k: v[0] for k, v in found.items()} == dict.fromkeys(found, "owned_by_residue")
    assert len(found) == 4
    assert {v[1] for v in found.values()} == {"assets/m/blockstates/door.json"}


def test_what_no_json_names_is_java_only(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/textures/gui/screen.png": PNG,
        "assets/m/textures/gui/screen.png.mcmeta": {"animation": {}},
        "assets/m/models/dynamic/fan.json": {"textures": {"all": "m:entity/fan"}},
        "assets/m/textures/entity/fan.png": PNG,
        "assets/m/atlases/blocks.json": {"sources": []},
    })
    files = ["assets/m/textures/gui/screen.png", "assets/m/textures/gui/screen.png.mcmeta",
             "assets/m/models/dynamic/fan.json", "assets/m/textures/entity/fan.png", "assets/m/atlases/blocks.json"]
    found = ownership.classify(root, files, consumed=set(), residue_sources=set())
    assert {k: v[0] for k, v in found.items()} == dict.fromkeys(files, "java_only_asset")


def test_a_file_a_shipped_model_names_stays_unowned(tmp_path):
    # The block shipped and its model was claimed, but a texture it names was
    # not: a converter missed it, which is not ours to explain away.
    root = _jar(tmp_path, {
        "assets/m/blockstates/lamp.json": {"variants": {"": {"model": "m:block/lamp"}}},
        "assets/m/models/block/lamp.json": {"textures": {"all": "m:block/lamp", "glow": "m:block/lamp_glow"}},
        "assets/m/textures/block/lamp_glow.png": PNG,
    })
    found = ownership.classify(root, ["assets/m/textures/block/lamp_glow.png"],
                               consumed={"assets/m/blockstates/lamp.json", "assets/m/models/block/lamp.json"},
                               residue_sources=set())
    assert found == {}


def test_an_unclaimed_top_level_item_model_is_left_alone(tmp_path):
    # Java loads models/item/<id>.json by the item's id: it may be an item's model.
    root = _jar(tmp_path, {"assets/m/models/item/gear.json": {"parent": "item/generated"}})
    assert ownership.classify(root, ["assets/m/models/item/gear.json"], set(), set()) == {}


def test_particle_sprites_go_with_their_definition(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/particles/spark.json": {"textures": ["m:spark_0", "m:spark_1"]},
        "assets/m/textures/particle/spark_0.png": PNG,
        "assets/m/textures/particle/spark_1.png": PNG,
    })
    unhandled = [Unhandled("assets/m/particles/", "unowned", "1 file(s) no converter claims yet", 1),
                 Unhandled("assets/m/textures/", "unowned", "2 file(s) no converter claims yet", 2)]
    out = ownership.refine(unhandled, root, consumed=set())
    kinds = sorted((u.kind, u.source, u.count) for u in out)
    assert kinds == [("owned_by_residue", "assets/m/textures/particle/", 2),
                     ("unowned", "assets/m/particles/", 1)]
    assert "assets/m/particles/spark.json" in next(u for u in out if u.kind == "owned_by_residue").reason


def test_refine_keeps_what_it_cannot_explain_as_unowned(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/blockstates/lamp.json": {"variants": {"": {"model": "m:block/lamp"}}},
        "assets/m/models/block/lamp.json": {"textures": {"glow": "m:block/lamp_glow"}},
        "assets/m/textures/block/lamp_glow.png": PNG,
        "assets/m/textures/gui/screen.png": PNG,
        "assets/m/textures/readme.txt": b"hi",
    })
    unhandled = [Unhandled("assets/m/textures/", "unowned", "3 file(s) no converter claims yet", 3),
                 Unhandled("data/m/recipes/x.json", "recipe", "nope")]
    out = ownership.refine(unhandled, root, consumed={"assets/m/blockstates/lamp.json",
                                                      "assets/m/models/block/lamp.json"})
    by_kind = {u.kind: u for u in out}
    assert by_kind["unowned"].count == 2 and by_kind["unowned"].reason.startswith("2 file(s)")
    assert by_kind["java_only_asset"].source == "assets/m/textures/gui/"
    assert by_kind["recipe"].source == "data/m/recipes/x.json"
    assert sum(u.count for u in out if u.kind != "recipe") == 3


def test_the_new_kinds_are_explained():
    from portkit.agent.residue import SKIP_KINDS

    for kind in ("owned_by_residue", "java_only_asset", "lang_code_string", "lang_unshipped",
                 "lang_locale", "lang_unreadable"):
        assert kind in SKIP_KINDS


def test_java_only_files_still_count_against_coverage(tmp_path, fixtures_dir):
    # Explained is not converted: re-filed files stay residue files.
    import shutil

    from portkit.pipeline import convert

    source = tmp_path / "mod"
    shutil.copytree(fixtures_dir / "simple_block_mod" / "input", source)
    for i in range(4):
        (source / "assets/examplemod/textures/gui").mkdir(parents=True, exist_ok=True)
        (source / f"assets/examplemod/textures/gui/s{i}.png").write_bytes(PNG)
    result = convert(source, tmp_path / "out")
    java_only = [u for u in result.unhandled if u.kind == "java_only_asset"]
    assert [(u.source, u.count) for u in java_only] == [("assets/examplemod/textures/gui/", 4)]
    assert not [u for u in result.unhandled if u.kind == "unowned"]
    assert result.residue_count == 4 and result.coverage < 100.0


def test_a_refused_block_s_item_model_hands_its_parent_to_the_block(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/blockstates/log.json": {"variants": {"axis=y": [{"model": "m:block/log"}, {"model": "m:block/log2"}]}},
        "assets/m/models/item/log.json": {"parent": "m:block/log"},
        "assets/m/models/block/log.json": {"parent": "block/cube_column"},
    })
    files = ["assets/m/models/block/log.json"]
    consumed = {"assets/m/blockstates/log.json", "assets/m/models/item/log.json"}
    residue = {"assets/m/blockstates/log.json"}
    # the item model was read, but the item didn't ship: the block owns it
    assert ownership.classify(root, files, consumed, residue, shipped=set()) == {
        "assets/m/models/block/log.json": ("owned_by_residue", "assets/m/blockstates/log.json")}
    # the item shipped: an unclaimed parent is a converter's miss, left alone
    assert ownership.classify(root, files, consumed, residue, shipped={"m:log"}) == {}


def test_an_obj_model_and_its_materials_follow_the_json_that_loads_it(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/blockstates/fan.json": {"variants": {"": {"model": "m:block/fan"}}},
        "assets/m/models/block/fan.json": {"loader": "neoforge:obj", "model": "m:models/block/fan.obj"},
        "assets/m/models/block/fan.obj": b"mtllib fan.mtl\nv 0 0 0\n",
        "assets/m/models/block/fan.mtl": b"newmtl a\n",
        "assets/m/models/block/loose.obj": b"v 0 0 0\n",
    })
    files = ["assets/m/models/block/fan.json", "assets/m/models/block/fan.obj",
             "assets/m/models/block/fan.mtl", "assets/m/models/block/loose.obj"]
    found = ownership.classify(root, files, consumed={"assets/m/blockstates/fan.json"},
                               residue_sources={"assets/m/blockstates/fan.json"})
    assert {k: v[0] for k, v in found.items()} == {
        "assets/m/models/block/fan.json": "owned_by_residue",
        "assets/m/models/block/fan.obj": "owned_by_residue",
        "assets/m/models/block/fan.mtl": "owned_by_residue",
        "assets/m/models/block/loose.obj": "java_only_asset",
    }


def test_a_texture_named_like_a_model_does_not_make_the_model_used(tmp_path):
    # #350: a shipped model's "textures" map names a texture whose path is also
    # a Java-only model's (Botania's spreader core: models/block/x_core.json,
    # loaded by its block-entity renderer, and textures/block/x_core.png). The
    # textures map names textures only, so the model has no JSON user.
    root = _jar(tmp_path, {
        "assets/m/blockstates/spreader.json": {"variants": {"": {"model": "m:block/spreader"}}},
        "assets/m/models/block/spreader.json": {"parent": "m:block/shape",
                                                "textures": {"core": "m:block/spreader_core"}},
        "assets/m/models/block/spreader_core.json": {"textures": {"core": "m:block/spreader_core"}},
        "assets/m/textures/block/spreader_core.png": PNG,
    })
    users = ownership.references(root)
    assert "assets/m/models/block/spreader_core.json" not in users
    assert "assets/m/models/block/spreader.json" in users["assets/m/textures/block/spreader_core.png"]
    found = ownership.classify(root, ["assets/m/models/block/spreader_core.json"],
                               consumed={"assets/m/blockstates/spreader.json",
                                         "assets/m/models/block/spreader.json"},
                               residue_sources=set())
    assert found == {"assets/m/models/block/spreader_core.json": ("java_only_asset", "")}


def test_a_newer_texture_object_still_names_its_sprite(tmp_path):
    root = _jar(tmp_path, {
        "assets/m/models/block/lamp.json": {"textures": {"all": {"sprite": "m:block/lamp"}}},
        "assets/m/textures/block/lamp.png": PNG,
    })
    assert ownership.references(root) == {
        "assets/m/textures/block/lamp.png": {"assets/m/models/block/lamp.json"}}
