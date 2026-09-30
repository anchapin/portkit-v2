"""End to end: the declared name and version reach the Bedrock manifest."""
import json

from portkit.pipeline import convert

PNG = b"\x89PNG\r\n\x1a\n"


def write_fixture(tmp_path):
    src = tmp_path / "src"
    block = src / "assets" / "examplemod" / "textures" / "block"
    block.mkdir(parents=True)
    (block / "stone_seat.png").write_bytes(PNG)
    (src / "fabric.mod.json").write_text(
        json.dumps(
            {
                "id": "examplemod",
                "version": "4.2.1+1.20.4",
                "name": "Example Mod",
                "description": "A mod that exists.",
            }
        )
    )
    return src


def test_manifest_carries_the_real_name_and_version(tmp_path):
    result = convert(write_fixture(tmp_path), tmp_path / "out")
    header = json.loads((result.tree / "resource_pack" / "manifest.json").read_text())["header"]
    assert header["name"] == "Example Mod (resource)"
    assert header["description"] == "A mod that exists."
    assert header["version"] == [4, 2, 1]
    assert result.report.ok
    assert result.notes == []


def test_summary_reports_the_mod_and_its_notes(tmp_path):
    summary = convert(write_fixture(tmp_path), tmp_path / "out").summary()
    assert summary["mod"] == {
        "name": "Example Mod",
        "id": "examplemod",
        "version": "4.2.1",
        "loader": "fabric",
    }
    assert summary["notes"] == []


def test_a_mod_with_no_metadata_still_converts_and_says_so(tmp_path):
    src = tmp_path / "src"
    block = src / "assets" / "examplemod" / "textures" / "block"
    block.mkdir(parents=True)
    (block / "x.png").write_bytes(PNG)
    result = convert(src, tmp_path / "out")
    header = json.loads((result.tree / "resource_pack" / "manifest.json").read_text())["header"]
    assert header["name"] == "examplemod (resource)"
    assert header["version"] == [0, 1, 0]
    assert any("no loader metadata" in n for n in result.notes)
