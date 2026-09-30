"""The mod's own declaration of who it is."""
import json

import pytest

from portkit.meta import ModMetadata, parse, parse_version


def test_fabric():
    blob = json.dumps(
        {
            "schemaVersion": 1,
            "id": "decorative_blocks",
            "version": "5.0.2+fabric",
            "name": "Decorative Blocks",
            "description": "Adds decorative blocks.",
        }
    ).encode()
    meta = parse({"fabric.mod.json": blob}, "decorative_blocks")
    assert (meta.mod_id, meta.name, meta.loader) == (
        "decorative_blocks",
        "Decorative Blocks",
        "fabric",
    )
    assert meta.version == (5, 0, 2)
    assert meta.notes == []


def test_quilt_reads_the_nested_shape():
    blob = json.dumps(
        {
            "quilt_loader": {
                "id": "examplemod",
                "version": "1.2.3",
                "metadata": {"name": "Example", "description": "Hi."},
            }
        }
    ).encode()
    meta = parse({"quilt.mod.json": blob}, "examplemod")
    assert (meta.mod_id, meta.name, meta.version, meta.loader) == (
        "examplemod",
        "Example",
        (1, 2, 3),
        "quilt",
    )


def test_forge_toml_including_a_multiline_description():
    blob = (
        b'modLoader="javafml"\n'
        b'loaderVersion="[47,)"\n'
        b'[[mods]]\n'
        b'modId="examplemod"\n'
        b'version="2.4.0"\n'
        b'displayName="Example Mod"\n'
        b'description="""Long text."""\n'
    )
    meta = parse({"META-INF/mods.toml": blob}, "examplemod")
    assert (meta.name, meta.version, meta.loader) == ("Example Mod", (2, 4, 0), "forge")
    assert meta.description == "Long text."


def test_neoforge_wins_over_forge_when_both_ship():
    forge = b'[[mods]]\nmodId="x"\nversion="1.0.0"\ndisplayName="Old"\n'
    neo = b'[[mods]]\nmodId="x"\nversion="2.0.0"\ndisplayName="New"\n'
    meta = parse({"META-INF/mods.toml": forge, "META-INF/neoforge.mods.toml": neo}, "x")
    assert (meta.name, meta.loader) == ("New", "neoforge")


def test_jar_version_placeholder_resolves_from_the_manifest():
    toml = b'[[mods]]\nmodId="x"\nversion="${file.jarVersion}"\ndisplayName="X"\n'
    manifest = b"Manifest-Version: 1.0\nImplementation-Version: 3.1.4\n"
    meta = parse({"META-INF/mods.toml": toml, "META-INF/MANIFEST.MF": manifest}, "x")
    assert meta.version == (3, 1, 4)
    assert any("resolved" in n for n in meta.notes)


def test_unresolved_placeholder_is_said_out_loud():
    toml = b'[[mods]]\nmodId="x"\nversion="${file.jarVersion}"\ndisplayName="X"\n'
    meta = parse({"META-INF/mods.toml": toml}, "x")
    assert meta.version == (0, 1, 0)
    assert any("placeholder" in n for n in meta.notes)


def test_legacy_mcmod_info():
    blob = json.dumps([{"modid": "x", "name": "X", "version": "1.7.10-1.0"}]).encode()
    meta = parse({"mcmod.info": blob}, "x")
    assert (meta.name, meta.version, meta.loader) == ("X", (1, 7, 10), "forge-legacy")


def test_no_metadata_falls_back_with_a_note():
    meta = parse({}, "examplemod")
    assert meta.name is None
    assert meta.version == (0, 1, 0)
    assert any("no loader metadata" in n for n in meta.notes)
    assert meta.header_name("examplemod", "behavior") == "examplemod (behavior)"


def test_broken_json_does_not_stop_the_conversion():
    meta = parse({"fabric.mod.json": b"{not json"}, "examplemod")
    assert any("could not be read" in n for n in meta.notes)
    assert meta.version == (0, 1, 0)


def test_mod_id_disagreeing_with_the_namespace_is_reported():
    blob = json.dumps({"id": "coolmod", "version": "1.0.0"}).encode()
    meta = parse({"fabric.mod.json": blob}, "cool_mod")
    assert any("does not match the resource namespace" in n for n in meta.notes)


def test_several_mods_in_one_toml_is_reported():
    blob = b'[[mods]]\nmodId="a"\nversion="1.0.0"\n[[mods]]\nmodId="b"\nversion="2.0.0"\n'
    meta = parse({"META-INF/mods.toml": blob}, "a")
    assert meta.mod_id == "a"
    assert any("declares 2 mods" in n for n in meta.notes)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1.2.3", (1, 2, 3)),
        ("5.0.2+fabric", (5, 0, 2)),
        ("2.0", (2, 0, 0)),
        ("7", (7, 0, 0)),
        ("1.20.4-0.3.1", (1, 20, 4)),
        ("v3.2.1", (3, 2, 1)),
        ("2.0.0-beta.4", (2, 0, 0)),
    ],
)
def test_version_parsing(raw, expected):
    assert parse_version(raw, []) == expected


def test_a_version_with_no_numbers_is_a_note_not_a_crash():
    notes = []
    assert parse_version("release-candidate", notes) == (0, 1, 0)
    assert notes


def test_header_prefers_name_then_id_then_namespace():
    assert ModMetadata(name="Nice").header_name("ns", "resource") == "Nice (resource)"
    assert ModMetadata(mod_id="nice_mod").header_name("ns", "resource") == "nice_mod (resource)"
    assert ModMetadata().header_description() == "Converted from Java by portkit"
