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


def _recipe(body_key, **fields):
    body = {"description": {"identifier": "examplemod:probe"}, "tags": ["crafting_table"]}
    body.update(fields)
    return {"format_version": "1.20.10", body_key: body}


def _recipe_findings(tmp_path, recipe):
    _write(tmp_path, "behavior_pack/manifest.json", _manifest())
    _write(tmp_path, "behavior_pack/recipes/probe.json", recipe)
    report = validate_tree(tmp_path)
    return [f for f in report.errors if f.rule == "recipe.empty"], report


def test_empty_shapeless_recipe_is_flagged(tmp_path):
    """#84: the probe file a model wrote to poke the validator must not pass."""
    empty, report = _recipe_findings(
        tmp_path, _recipe("minecraft:recipe_shapeless", ingredients=[], result=[])
    )
    assert not report.ok
    assert {f.message.split()[0] for f in empty} == {"ingredients", "result"}


def test_missing_result_on_shaped_recipe_is_flagged(tmp_path):
    empty, _ = _recipe_findings(
        tmp_path,
        _recipe("minecraft:recipe_shaped", pattern=["#"], key={"#": {"item": "m:b"}}),
    )
    assert [f.message.split()[0] for f in empty] == ["result"]


def test_list_of_empty_ingredients_is_flagged(tmp_path):
    empty, _ = _recipe_findings(
        tmp_path,
        _recipe("minecraft:recipe_shapeless", ingredients=[{}], result={"item": "m:a"}),
    )
    assert [f.message.split()[0] for f in empty] == ["ingredients"]


def test_empty_furnace_recipe_is_flagged(tmp_path):
    empty, _ = _recipe_findings(
        tmp_path, _recipe("minecraft:recipe_furnace", input="", output="")
    )
    assert {f.message.split()[0] for f in empty} == {"input", "output"}


def test_filled_shapeless_recipe_has_no_empty_finding(tmp_path):
    empty, report = _recipe_findings(
        tmp_path,
        _recipe(
            "minecraft:recipe_shapeless",
            ingredients=[{"item": "minecraft:iron_ingot"}],
            result={"item": "minecraft:iron_nugget", "count": 9},
        ),
    )
    assert empty == []
    assert report.ok


def test_non_object_recipe_body_is_flagged_not_crashing(tmp_path):
    _write(tmp_path, "behavior_pack/manifest.json", _manifest())
    _write(tmp_path, "behavior_pack/recipes/probe.json",
           {"format_version": "1.20.10", "minecraft:recipe_shapeless": "oops"})
    report = validate_tree(tmp_path)
    assert any(f.rule == "recipe.shape" for f in report.errors)


def test_furnace_recipe_with_result_key_is_accepted(tmp_path):
    """The converter emits the furnace family's product as "result"; keep it passing."""
    empty, _ = _recipe_findings(
        tmp_path,
        _recipe("minecraft:recipe_furnace", input={"item": "m:ore"}, result={"item": "m:ingot"}),
    )
    assert empty == []


def test_smithing_transform_needs_all_four_slots(tmp_path):
    """#87: Bedrock's smithing recipe takes template, base, addition and result."""
    empty, _ = _recipe_findings(
        tmp_path,
        _recipe("minecraft:recipe_smithing_transform", base="m:a", result="m:b"),
    )
    assert {f.message.split()[0] for f in empty} == {"template", "addition"}
