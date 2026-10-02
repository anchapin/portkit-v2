"""A converted pack's .lang files land on disk as plain lines, not JSON."""
from portkit.model import ConversionResult
from portkit.pack import write_tree


def test_lang_files_are_written_as_plain_text(tmp_path):
    result = ConversionResult()
    result.files["texts/en_US.lang"] = "tile.demo:oak_seat.name=Oak Seat\ntile.demo:oak_beam.name=Oak Beam\n"
    result.files["texts/languages.json"] = ["en_US"]
    write_tree(result, "demo", tmp_path)
    text = (tmp_path / "resource_pack/texts/en_US.lang").read_text(encoding="utf-8")
    assert text.splitlines() == ["tile.demo:oak_seat.name=Oak Seat", "tile.demo:oak_beam.name=Oak Beam"]
    assert not text.startswith('"')
    assert (tmp_path / "resource_pack/texts/languages.json").read_text().strip().startswith("[")
