import json

from portkit.validate import validate_tree


def _write(tmp_path, relpath, data):
    target = tmp_path / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2))
    return target


def _manifest():
    return {
        "format_version": 2,
        "header": {
            "name": "t",
            "uuid": "11111111-1111-1111-1111-111111111111",
            "version": [1, 0, 0],
            "min_engine_version": [1, 20, 10],
        },
        "modules": [
            {"type": "data", "uuid": "22222222-2222-2222-2222-222222222222", "version": [1, 0, 0]}
        ],
    }


def test_clean_pack_passes(tmp_path):
    _write(tmp_path, "behavior_pack/manifest.json", _manifest())
    _write(
        tmp_path,
        "behavior_pack/recipes/a.json",
        {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": "m:a"},
                "tags": ["crafting_table"],
                "pattern": ["##", "##"],
                "key": {"#": {"item": "m:b"}},
                "result": {"item": "m:a"},
            },
        },
    )
    assert validate_tree(tmp_path).ok


def test_pattern_symbol_without_key_is_an_error(tmp_path):
    _write(tmp_path, "behavior_pack/manifest.json", _manifest())
    _write(
        tmp_path,
        "behavior_pack/recipes/a.json",
        {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": "m:a"},
                "tags": ["crafting_table"],
                "pattern": ["#X", "##"],
                "key": {"#": {"item": "m:b"}},
                "result": {"item": "m:a"},
            },
        },
    )
    report = validate_tree(tmp_path)
    assert not report.ok
    assert any(f.rule == "recipe.key" for f in report.errors)


def test_duplicate_uuid_is_caught(tmp_path):
    manifest = _manifest()
    manifest["modules"][0]["uuid"] = manifest["header"]["uuid"]
    _write(tmp_path, "behavior_pack/manifest.json", manifest)
    report = validate_tree(tmp_path)
    assert any(f.rule == "manifest.uuid_unique" for f in report.errors)


def test_texture_index_pointing_at_nothing_is_caught(tmp_path):
    _write(tmp_path, "resource_pack/manifest.json", _manifest())
    _write(
        tmp_path,
        "resource_pack/textures/terrain_texture.json",
        {"texture_data": {"m:ghost": {"textures": "textures/blocks/ghost"}}},
    )
    report = validate_tree(tmp_path)
    assert any(f.rule == "texture_index.missing" for f in report.errors)


def test_top_level_string_recipe_does_not_crash(tmp_path):
    """A recipe file whose contents parse to a string at the top level (a model
    wrote ``content="<json-string>"`` instead of a dict) must be reported as a
    parse error and not raise ``AttributeError`` from ``.items()`` on a string.

    Discovered by the model sweep: deepseek-v4.1-flash produced such a file and
    the validator crashed, masking the real write from the residue report.
    """
    _write(tmp_path, "behavior_pack/manifest.json", _manifest())
    # Write a JSON-encoded string at the top level — what a misbehaving tool
    # call would produce.
    target = tmp_path / "behavior_pack" / "recipes" / "broken.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('"oops"')
    # Either flagged as json.parse by another rule, or skipped cleanly — never
    # an exception.
    report = validate_tree(tmp_path)
    assert report is not None


def test_top_level_string_item_does_not_crash(tmp_path):
    """Same defense on the items xref path; a model could write a string there too."""
    _write(tmp_path, "behavior_pack/manifest.json", _manifest())
    target = tmp_path / "behavior_pack" / "items" / "broken.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('"oops"')
    # Should not raise.
    report = validate_tree(tmp_path)
    assert report is not None
